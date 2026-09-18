import io

from django.core.management import call_command
from django.test import TestCase

from ..models import Entity, EntityType, Execution, Executor, Project

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class WipePlatformDataTests(TestCase):
    def test_wipe_with_entities_does_not_recurse_infinitely(self):
        # Django's delete collector cascades EntityType -> Entity by fetching entities with only
        # their FK columns loaded (state/data deferred) - Entity.__init__ used to dereference
        # both of those unconditionally, which ping-ponged between refresh_from_db() calls
        # forever. A handful of entities is enough to hit that path.
        entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        project = Project.objects.create(name="project-1")
        for i in range(5):
            Entity.objects.create(
                entitytype=entitytype, project=project, data={"address": f"1.1.1.{i}"}, state=Entity.STATE_ENABLED
            )

        call_command("wipe_platform_data", "--noinput", stdout=io.StringIO())

        self.assertEqual(Entity.objects.count(), 0)
        self.assertEqual(EntityType.objects.count(), 0)
        self.assertEqual(Project.objects.count(), 0)

    def test_wipe_deletes_everything(self):
        from ..models import Container, WorkerProfile

        project = Project.objects.create(name="project-1")
        entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        container = Container.objects.create(name="c1", image="img")
        executor = Executor.objects.create(name="ex1", container=container)
        WorkerProfile.objects.create(name="wp1")
        Execution.objects.create(project=project, executor=executor, state=Execution.STATE_MANUAL)
        Entity.objects.create(
            entitytype=entitytype, project=project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

        call_command("wipe_platform_data", "--noinput", stdout=io.StringIO())

        self.assertEqual(Project.objects.count(), 0)
        self.assertEqual(EntityType.objects.count(), 0)
        self.assertEqual(Container.objects.count(), 0)
        self.assertEqual(Executor.objects.count(), 0)
        self.assertEqual(WorkerProfile.objects.count(), 0)
        self.assertEqual(Execution.objects.count(), 0)
        self.assertEqual(Entity.objects.count(), 0)
