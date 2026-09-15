from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Container, EntityType, Executor, WorkerProfile
from squiggle_automation.testutils import random_password

User = get_user_model()

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class ExecutorApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.container = Container.objects.create(name="container", image="alpine")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:executor-list"))
        self.assertEqual(r.status_code, 401)

    def test_list_executors(self):
        Executor.objects.create(name="executor-a", container=self.container)
        Executor.objects.create(name="executor-b", container=self.container)

        r = self.client.get(reverse("api:executor-list"))
        self.assertEqual(r.status_code, 200)

        names = [e["name"] for e in r.data]
        self.assertIn("executor-a", names)
        self.assertIn("executor-b", names)

    def test_retrieve_executor(self):
        executor = Executor.objects.create(name="executor-retrieve", container=self.container)

        r = self.client.get(reverse("api:executor-detail", args=[executor.name]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "executor-retrieve")
        self.assertEqual(r.data["container"], self.container.name)
        self.assertNotIn("id", r.data)

    def test_create_executor(self):
        r = self.client.post(
            reverse("api:executor-list"),
            {"name": "new-executor", "container": self.container.name, "max_entities": 50},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)

        executor = Executor.objects.get(name="new-executor")
        self.assertEqual(executor.max_entities, 50)
        self.assertTrue(executor.enabled)

    def test_create_executor_with_input_output_and_workerprofile(self):
        entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        workerprofile = WorkerProfile.objects.create(name="low")

        r = self.client.post(
            reverse("api:executor-list"),
            {
                "name": "executor-with-relations",
                "container": self.container.name,
                "input": [entitytype.name],
                "output": [entitytype.name],
                "workerprofile": workerprofile.name,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["input"], [entitytype.name])
        self.assertEqual(r.data["output"], [entitytype.name])
        self.assertEqual(r.data["workerprofile"], workerprofile.name)

        executor = Executor.objects.get(name="executor-with-relations")
        self.assertEqual(list(executor.input.all()), [entitytype])
        self.assertEqual(list(executor.output.all()), [entitytype])
        self.assertEqual(executor.workerprofile, workerprofile)

    def test_create_executor_with_unknown_workerprofile_name_is_rejected(self):
        r = self.client.post(
            reverse("api:executor-list"),
            {"name": "executor-bad-worker", "container": self.container.name, "workerprofile": "does-not-exist"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Executor.objects.filter(name="executor-bad-worker").exists())

    def test_update_executor(self):
        executor = Executor.objects.create(name="to-update", container=self.container)

        r = self.client.patch(
            reverse("api:executor-detail", args=[executor.name]),
            {"enabled": False},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        executor.refresh_from_db()
        self.assertFalse(executor.enabled)

    def test_delete_executor(self):
        executor = Executor.objects.create(name="to-delete", container=self.container)

        r = self.client.delete(reverse("api:executor-detail", args=[executor.name]))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Executor.objects.filter(pk=executor.pk).exists())
