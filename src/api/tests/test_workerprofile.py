from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import WorkerProfile
from squiggle_automation.testutils import random_password

User = get_user_model()


class WorkerProfileApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:workerprofile-list"))
        self.assertEqual(r.status_code, 401)

    def test_list_workerprofiles(self):
        WorkerProfile.objects.create(name="low")
        WorkerProfile.objects.create(name="high")

        r = self.client.get(reverse("api:workerprofile-list"))
        self.assertEqual(r.status_code, 200)

        names = [w["name"] for w in r.data]
        self.assertIn("low", names)
        self.assertIn("high", names)

    def test_retrieve_workerprofile(self):
        worker = WorkerProfile.objects.create(name="retrieve-me")

        r = self.client.get(reverse("api:workerprofile-detail", args=[worker.name]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "retrieve-me")
        self.assertNotIn("id", r.data)

    def test_first_created_workerprofile_becomes_default(self):
        r = self.client.post(reverse("api:workerprofile-list"), {"name": "first"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(WorkerProfile.objects.get(name="first").is_default)

    def test_second_created_workerprofile_is_not_default(self):
        WorkerProfile.objects.create(name="first")

        r = self.client.post(reverse("api:workerprofile-list"), {"name": "second"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(WorkerProfile.objects.get(name="second").is_default)

    def test_create_workerprofile_named_default_is_rejected(self):
        r = self.client.post(reverse("api:workerprofile-list"), {"name": "default"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(WorkerProfile.objects.filter(name="default").exists())

    def test_update_workerprofile_concurrency(self):
        worker = WorkerProfile.objects.create(name="to-update")

        r = self.client.patch(
            reverse("api:workerprofile-detail", args=[worker.name]), {"concurrency": 10}, format="json"
        )
        self.assertEqual(r.status_code, 200, r.content)

        worker.refresh_from_db()
        self.assertEqual(worker.concurrency, 10)

    def test_update_workerprofile_name_is_read_only(self):
        worker = WorkerProfile.objects.create(name="original-name")

        r = self.client.patch(
            reverse("api:workerprofile-detail", args=[worker.name]), {"name": "renamed"}, format="json"
        )
        self.assertEqual(r.status_code, 200, r.content)

        worker.refresh_from_db()
        self.assertEqual(worker.name, "original-name")

    def test_delete_default_workerprofile_is_rejected(self):
        worker = WorkerProfile.objects.create(name="only-one")
        self.assertTrue(worker.is_default)

        r = self.client.delete(reverse("api:workerprofile-detail", args=[worker.name]))
        self.assertEqual(r.status_code, 400)
        self.assertTrue(WorkerProfile.objects.filter(pk=worker.pk).exists())

    def test_delete_non_default_workerprofile(self):
        WorkerProfile.objects.create(name="default-one")
        worker = WorkerProfile.objects.create(name="not-default")
        self.assertFalse(worker.is_default)

        r = self.client.delete(reverse("api:workerprofile-detail", args=[worker.name]))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(WorkerProfile.objects.filter(pk=worker.pk).exists())
