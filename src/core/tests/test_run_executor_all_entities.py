from unittest.mock import patch

from django.test import TestCase

from ..models import Container, Entity, EntityType, Event, Executor, Project
from ..tasks import run_executor_all_entities

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class RunExecutorAllEntitiesTests(TestCase):
    def setUp(self):
        # entitytype must exist before the projects so that index creation works (see EntityType.save())
        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.other_entitytype = EntityType.objects.create(name="other", schema=SCHEMA, identifier_keys="address")
        self.project = Project.objects.create(name="project-1")

        container = Container.objects.create(name="container", image="image")
        self.executor = Executor.objects.create(name="my-executor", container=container, max_entities=100)
        self.executor.input.set([self.entitytype])

    def test_deleted_executor_is_silently_ignored(self):
        executor_id = self.executor.pk
        self.executor.delete()

        run_executor_all_entities(executor_id, self.project.pk)  # must not raise

    def test_deleted_project_is_silently_ignored(self):
        project_id = self.project.pk
        self.project.delete()

        run_executor_all_entities(self.executor.pk, project_id)  # must not raise

    def test_fills_execution_with_matching_enabled_entities_only(self):
        matching = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "2.2.2.2"},
            state=Entity.STATE_DISABLED,
        )
        Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "3.3.3.3"},
            state=Entity.STATE_WAITING_APPROVAL,
        )
        Entity.objects.create(
            entitytype=self.other_entitytype,
            project=self.project,
            data={"address": "4.4.4.4"},
            state=Entity.STATE_ENABLED,
        )

        with patch("core.models.execution.Execution.schedule"):
            run_executor_all_entities(self.executor.pk, self.project.pk)

        execution = self.executor.execution_set.get()
        self.assertEqual(list(execution.entities.all()), [matching])

    def test_does_not_create_events(self):
        Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        # creating the entity above already added its own Event (see Entity.save()) - that one is
        # not what this test is about, only the task must not add another one
        Event.objects.all().delete()

        with patch("core.models.execution.Execution.schedule"):
            run_executor_all_entities(self.executor.pk, self.project.pk)

        self.assertEqual(Event.objects.count(), 0)

    def test_runs_even_when_project_executors_are_disabled(self):
        # unlike run_event_handler's automatic triggering (which respects run_executors, see
        # run_event_handler.py), this task backs the "run now" button - a manual, explicit
        # request that must go through even if automatic runs are paused for the project.
        self.project.run_executors = False
        self.project.save()

        Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

        with patch("core.models.execution.Execution.schedule"):
            run_executor_all_entities(self.executor.pk, self.project.pk)

        self.assertTrue(self.executor.execution_set.exists())

    def test_schedules_execution_once_max_entities_is_reached(self):
        self.executor.max_entities = 1
        self.executor.save()

        Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

        with patch("core.models.execution.Execution.schedule") as mock_schedule:
            run_executor_all_entities(self.executor.pk, self.project.pk)

        mock_schedule.assert_called_once()

    def test_no_matching_entities_creates_no_execution(self):
        run_executor_all_entities(self.executor.pk, self.project.pk)

        self.assertFalse(self.executor.execution_set.exists())
