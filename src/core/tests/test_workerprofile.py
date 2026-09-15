import json

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from api.serializers import WorkerProfileSerializer
from squiggle_automation.testutils import random_password

from ..models import WorkerProfile

User = get_user_model()


class WorkerProfileTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)


class WorkerProfileListViewTests(WorkerProfileTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:workerprofiles"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_worker_profiles(self):
        WorkerProfile.objects.create(name="w-b")
        WorkerProfile.objects.create(name="w-a")

        r = self.client.get(reverse("core:workerprofiles"))
        self.assertEqual(r.status_code, 200)

        names = [w.name for w in r.context["workers"]]
        self.assertEqual(names, ["w-a", "w-b"])

    def test_shows_json_matching_the_api_serializer(self):
        worker = WorkerProfile.objects.create(name="w-json")

        r = self.client.get(reverse("core:workerprofiles"))
        self.assertEqual(r.status_code, 200)

        expected_json = json.dumps(WorkerProfileSerializer(worker).data, indent=2)
        self.assertContains(r, escape(expected_json))
        self.assertContains(r, f'data-bs-target="#workerprofile-json-{worker.pk}"')
        self.assertContains(r, f'id="workerprofile-json-{worker.pk}-content"')


class WorkerProfileCreateViewTests(WorkerProfileTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:workerprofile-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_worker_profile(self):
        r = self.client.post(
            reverse("core:workerprofile-create"),
            {"name": "worker-1", "concurrency": 3},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:workerprofiles"))

        worker = WorkerProfile.objects.get(name="worker-1")
        self.assertEqual(worker.concurrency, 3)

    def test_post_name_default_is_rejected(self):
        r = self.client.post(
            reverse("core:workerprofile-create"),
            {"name": "default", "concurrency": 3},
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(WorkerProfile.objects.filter(name="default").exists())

    def test_first_created_worker_profile_becomes_default(self):
        self.client.post(reverse("core:workerprofile-create"), {"name": "worker-1", "concurrency": 3})

        worker = WorkerProfile.objects.get(name="worker-1")
        self.assertTrue(worker.is_default)

    def test_marking_new_worker_profile_as_default_unmarks_previous_default(self):
        first = WorkerProfile.objects.create(name="worker-first")
        self.assertTrue(first.is_default)

        self.client.post(
            reverse("core:workerprofile-create"),
            {"name": "worker-second", "concurrency": 5, "is_default": "on"},
        )

        first.refresh_from_db()
        second = WorkerProfile.objects.get(name="worker-second")
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)


class WorkerProfileUpdateViewTests(WorkerProfileTestCase):
    def setUp(self):
        super().setUp()
        self.worker = WorkerProfile.objects.create(name="original")

    def test_get_ok(self):
        r = self.client.get(reverse("core:workerprofile-update", args=[self.worker.pk]))
        self.assertEqual(r.status_code, 200)

    def test_post_updates_concurrency(self):
        r = self.client.post(
            reverse("core:workerprofile-update", args=[self.worker.pk]),
            {"concurrency": 9, "is_default": "on"},
        )
        self.assertEqual(r.status_code, 302)

        self.worker.refresh_from_db()
        self.assertEqual(self.worker.concurrency, 9)

    def test_name_is_not_editable(self):
        # "name" is intentionally not in the update form's fields
        r = self.client.get(reverse("core:workerprofile-update", args=[self.worker.pk]))
        self.assertNotIn("name", r.context["form"].fields)


class WorkerProfileDeleteViewTests(WorkerProfileTestCase):
    def test_get_shows_confirmation(self):
        WorkerProfile.objects.create(name="first")
        second = WorkerProfile.objects.create(name="to-delete")

        r = self.client.get(reverse("core:workerprofile-delete", args=[second.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "to-delete")

    def test_post_deletes_non_default_worker_profile(self):
        WorkerProfile.objects.create(name="first")  # becomes default
        second = WorkerProfile.objects.create(name="to-delete2")
        self.assertFalse(second.is_default)

        r = self.client.post(reverse("core:workerprofile-delete", args=[second.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(WorkerProfile.objects.filter(pk=second.pk).exists())

    def test_post_deleting_default_worker_profile_shows_error_instead_of_500(self):
        worker = WorkerProfile.objects.create(name="only-one")
        self.assertTrue(worker.is_default)

        r = self.client.post(reverse("core:workerprofile-delete", args=[worker.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:workerprofiles"))

        # the worker profile was not deleted
        self.assertTrue(WorkerProfile.objects.filter(pk=worker.pk).exists())

        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("Cannot delete the default worker" in str(m) for m in messages))


class WorkerProfileModelTests(TestCase):
    def test_delete_raises_validation_error_for_default_worker(self):
        worker = WorkerProfile.objects.create(name="the-default")
        self.assertTrue(worker.is_default)

        with self.assertRaises(ValidationError):
            worker.delete()

    def test_deleting_default_promotes_another_worker(self):
        first = WorkerProfile.objects.create(name="first")
        second = WorkerProfile.objects.create(name="second")
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

        # cannot delete the default directly...
        with self.assertRaises(ValidationError):
            first.delete()

        # ...but once it is no longer default, deletion works
        second.is_default = True
        second.save()
        first.refresh_from_db()
        self.assertFalse(first.is_default)

        first.delete()
        self.assertFalse(WorkerProfile.objects.filter(pk=first.pk).exists())
