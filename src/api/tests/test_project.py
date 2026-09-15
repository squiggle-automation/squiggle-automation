import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Project
from squiggle_automation.testutils import random_password

User = get_user_model()


class ProjectApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:project-list"))
        self.assertEqual(r.status_code, 401)

    def test_list_projects(self):
        Project.objects.create(name="proj-a")
        Project.objects.create(name="proj-b")

        r = self.client.get(reverse("api:project-list"))
        self.assertEqual(r.status_code, 200)

        names = [p["name"] for p in r.data]
        self.assertIn("proj-a", names)
        self.assertIn("proj-b", names)

    def test_retrieve_project(self):
        project = Project.objects.create(name="proj-retrieve")

        r = self.client.get(reverse("api:project-detail", args=[project.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "proj-retrieve")

    def test_create_project(self):
        r = self.client.post(reverse("api:project-list"), {"name": "new-project", "run_executors": True}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(Project.objects.filter(name="new-project").exists())

    def test_create_project_via_form_data(self):
        r = self.client.post(
            reverse("api:project-list"), {"name": "form-project", "run_executors": True}, format="multipart"
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(Project.objects.filter(name="form-project").exists())

    def test_html_accept_header_returns_browsable_api(self):
        r = self.client.get(reverse("api:project-list"), HTTP_ACCEPT="text/html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r["Content-Type"])

    def test_session_auth_get_works(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)

        r = client.get(reverse("api:project-list"))
        self.assertEqual(r.status_code, 200)

    def test_session_auth_post_without_csrf_token_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)

        r = client.post(reverse("api:project-list"), {"name": "csrf-project"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Project.objects.filter(name="csrf-project").exists())

    def test_update_project(self):
        project = Project.objects.create(name="to-update")

        r = self.client.patch(
            reverse("api:project-detail", args=[project.pk]),
            data=json.dumps({"run_executors": False}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        project.refresh_from_db()
        self.assertFalse(project.run_executors)

    def test_delete_project(self):
        project = Project.objects.create(name="to-delete")

        r = self.client.delete(reverse("api:project-detail", args=[project.pk]))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())
