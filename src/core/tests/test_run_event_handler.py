import threading
from unittest.mock import patch

from django.core.cache import caches
from django.db import connections
from django.test import TestCase, TransactionTestCase

from ..models import (
    Container,
    Entity,
    EntityType,
    Execution,
    Executor,
    Project,
    WorkerProfile,
)
from ..tasks import run_executor as run_executor_task
from ..tasks.run_event_handler import _fill_executions, run_event_handler

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class FillExecutionsTests(TestCase):
    def setUp(self):
        # entitytype must exist before the project so that index creation works (see EntityType.save())
        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.project = Project.objects.create(name="project-1")
        container = Container.objects.create(name="container", image="image")
        self.executor = Executor.objects.create(name="my-executor", container=container, max_entities=2)
        self.executor.input.set([self.entitytype])

    def _make_entities(self, count, offset=0):
        return [
            Entity.objects.create(
                entitytype=self.entitytype,
                project=self.project,
                data={"address": f"1.1.1.{offset + i}"},
                state=Entity.STATE_ENABLED,
            )
            for i in range(count)
        ]

    def test_fills_and_creates_executions_as_needed(self):
        entities = self._make_entities(3)

        with patch("core.models.execution.Execution.schedule"):
            _fill_executions(self.project, self.executor, entities)

        executions = list(Execution.objects.filter(project=self.project, executor=self.executor))
        # 2 entities fill up the first execution (max_entities=2), the third spills into a new one
        self.assertEqual(len(executions), 2)
        counts = sorted(e.entities.count() for e in executions)
        self.assertEqual(counts, [1, 2])

    def test_schedules_execution_exactly_once_when_full(self):
        entities = self._make_entities(2)

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            _fill_executions(self.project, self.executor, entities)

        mock_schedule.assert_called_once()

    def test_does_not_schedule_execution_below_max_entities(self):
        entities = self._make_entities(1)

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            _fill_executions(self.project, self.executor, entities)

        mock_schedule.assert_not_called()
        execution = Execution.objects.get(project=self.project, executor=self.executor)
        self.assertEqual(execution.state, Execution.STATE_FILLING)

    def test_does_not_reschedule_an_already_full_execution_across_loop_rounds(self):
        # regression test: schedule() must flip the execution's state synchronously (only the
        # actual task dispatch inside it is deferred, see Execution.schedule()) so that a later
        # round of _fill_executions' while-loop - triggered here by needing to create a second
        # execution for the leftover entities - does not match the already-full first one again
        # and schedule it a second time. Deliberately does NOT mock schedule() itself, since
        # that would also mask this state transition and hide the bug.
        WorkerProfile.objects.create(name="worker-queue")  # becomes default automatically
        entities = self._make_entities(2 + 2)  # exactly fills two executions of max_entities=2

        with patch.object(run_executor_task, "apply_async") as mock_apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                _fill_executions(self.project, self.executor, entities)

        self.assertEqual(mock_apply_async.call_count, 2)
        executions = Execution.objects.filter(project=self.project, executor=self.executor)
        self.assertEqual(set(executions.values_list("state", flat=True)), {Execution.STATE_QUEUED})


class FillExecutionsConcurrencyTests(TransactionTestCase):
    """
    Regression tests for the race fixed in _fill_executions(): concurrent callers (e.g.
    run_event_handler and run_executor_all_entities running at the same time for the same
    executor) must not be able to overfill an execution or schedule it more than once.
    """

    def setUp(self):
        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.project = Project.objects.create(name="project-1")
        container = Container.objects.create(name="container", image="image")
        self.executor = Executor.objects.create(name="my-executor", container=container, max_entities=5)
        self.executor.input.set([self.entitytype])

    def _make_entities(self, count, offset=0):
        return [
            Entity.objects.create(
                entitytype=self.entitytype,
                project=self.project,
                data={"address": f"1.1.1.{offset + i}"},
                state=Entity.STATE_ENABLED,
            )
            for i in range(count)
        ]

    def test_concurrent_calls_do_not_overfill_or_double_schedule(self):
        # two batches that together exactly fill exactly two executions (5 entities each)
        batch_a = self._make_entities(5, offset=0)
        batch_b = self._make_entities(5, offset=5)

        barrier = threading.Barrier(2)
        errors = []

        def run(entities):
            try:
                barrier.wait(timeout=5)
                with patch("core.models.execution.Execution.schedule"):
                    _fill_executions(self.project, self.executor, entities)
            except Exception as exc:  # pragma: no cover - surfaced via errors list below
                errors.append(exc)
            finally:
                # each thread uses its own connection; make sure it's cleaned up
                connections.close_all()

        threads = [threading.Thread(target=run, args=(batch,)) for batch in (batch_a, batch_b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [])

        executions = list(Execution.objects.filter(project=self.project, executor=self.executor))
        total_entities = sum(e.entities.count() for e in executions)

        # all 10 entities must be accounted for, none dropped and none duplicated into the
        # same execution twice
        self.assertEqual(total_entities, 10)
        # no execution may ever exceed max_entities, even though both threads raced to fill them
        for execution in executions:
            self.assertLessEqual(execution.entities.count(), self.executor.max_entities)


class RunEventHandlerLockTests(TransactionTestCase):
    def test_skips_run_when_lock_is_already_held(self):
        Project.objects.create(name="project-1", run_executors=True)

        # simulate another worker already holding the lock
        caches["locks"].add("run_event_handler", "some-other-worker", 60)
        try:
            with patch("core.tasks.run_event_handler._fill_executions") as mock_fill:
                run_event_handler()
            mock_fill.assert_not_called()
        finally:
            caches["locks"].delete("run_event_handler")
