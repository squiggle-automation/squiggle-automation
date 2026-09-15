from celery import shared_task

from core.models import Entity, Executor, Project

from .run_event_handler import _fill_executions

# TODO: log errors, show them, etc. (see run_event_handler.py)


@shared_task
def run_executor_all_entities(executor_id, project_id):
    """
    Create new executions for this executor with all existing entities.
    """
    try:
        executor = Executor.objects.get(pk=executor_id)
    except Executor.DoesNotExist:
        return  # executor was deleted before this task ran

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return  # project was deleted before this task ran

    # TODO: run in chunks?
    entities = list(
        Entity.objects.filter(
            project=project,
            entitytype__in=executor.input.all(),
            state=Entity.STATE_ENABLED,
        )
    )

    if entities:
        _fill_executions(project, executor, entities)
