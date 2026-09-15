from celery import shared_task
from django.db import transaction

from core.models import Entity, Event, Execution, Executor, Project
from squiggle_automation.utils import cache_lock

# TODO: log errors, show them, etc.


@shared_task(bind=True)
def run_event_handler(self):
    """Handle the open events by creating and scheduling the executions."""
    with cache_lock("run_event_handler", self.app.oid) as acquired:
        if not acquired:
            return  # lock timeouted, we did not get it

        # handle projects separately
        for project in Project.objects.filter(run_executors=True):
            # get some events
            # TODO: limit? to config? loop around events until all events are done or max X times
            events = list(
                Event.objects.filter(project=project)
                .select_related("entity__entitytype")
                .order_by("entity__entitytype")
                .all()[:5000]
            )

            # fill / create the executions
            #
            # get entitytypes of open events
            entitytypes_with_events = set(event.entity.entitytype for event in events)
            for entitytype in entitytypes_with_events:
                # search for executors that need to be triggered
                for executor in Executor.objects.filter(input=entitytype, enabled=True):
                    # search for entities that have the required entitytype (and are enabled - just to be sure that this has not changed)
                    entities = [
                        event.entity
                        for event in events
                        if event.entity.entitytype == entitytype and event.entity.state == Entity.STATE_ENABLED
                    ]

                    # fill / create executions with entities
                    _fill_executions(project, executor, entities)

            # delete the handled events
            event_ids = [event.id for event in events]
            Event.objects.filter(id__in=event_ids).delete()

            # schedule executions that are over time or full
            _run_executions_after_timeout(project)


def _fill_executions(project, executor, entities):
    """
    Fill / create executions of this executor with the given entities, scheduling one as soon
    as it reaches max_entities.

    Safe to call concurrently for the same executor (e.g. from run_event_handler and
    run_executor_all_entities running at the same time): each round below locks the Executor row
    (select_for_update) for the duration of the read-modify-write, so only one caller at a time
    can fill/create Execution(s) for it. Without this, two concurrent callers could each read the
    same "slots missing" count and together overfill an execution, schedule it twice, or both
    create a new filling execution.
    """
    entities = entities.copy()

    while True:
        with transaction.atomic():
            # lock the executor so concurrent calls for it are serialized; this also covers the
            # case where executions_filling below is empty, which a lock on Execution rows alone
            # would not
            executor = Executor.objects.select_for_update().get(pk=executor.pk)

            # check if there is an execution that can be filled
            executions_filling = Execution.objects.select_for_update().filter(
                project=project, executor=executor, state=Execution.STATE_FILLING
            )
            for execution in executions_filling:
                # check how many entities we can put into this execution
                num_missing = execution.max_entities_missing
                if num_missing > 0:
                    # get the entities for this execution and remove it from big list
                    entities_tmp = entities[:num_missing]
                    del entities[:num_missing]

                    execution.entities.add(*entities_tmp)

                # max number of entities reached now? -> schedule it now (this flips its state to
                # STATE_QUEUED synchronously, so later rounds of this loop no longer match it in
                # the STATE_FILLING filter above; the actual task dispatch inside schedule() is
                # itself deferred until this transaction commits, see Execution.schedule())
                if execution.max_entities_missing == 0:
                    execution.schedule()

            # check if entities are left
            if len(entities) > 0:
                # if yes, create a new execution and fill it in next round
                Execution.objects.create(project=project, executor=executor, state=Execution.STATE_FILLING)
            else:
                # if no, we are done
                return


def _run_executions_after_timeout(project):
    executions_filling = Execution.objects.filter(project=project, state=Execution.STATE_FILLING).prefetch_related(
        "executor"
    )
    for e in executions_filling:
        if e.max_entities_timeout_reached:
            with transaction.atomic():
                # lock and re-check: _fill_executions() may have concurrently filled/scheduled
                # this execution already, in which case it is no longer STATE_FILLING
                execution = Execution.objects.select_for_update().get(pk=e.pk)
                if execution.state == Execution.STATE_FILLING and execution.max_entities_timeout_reached:
                    execution.schedule()
