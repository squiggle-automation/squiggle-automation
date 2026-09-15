from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from squiggle_automation.testutils import random_password

from ..models import Project

User = get_user_model()


class CoreLoginTestCase(TestCase):
    """Base class that logs in as a plain (non-superuser) user, as required by all core views."""

    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)


class ProjectOptionalMixinTests(CoreLoginTestCase):
    """Exercised via ProjectListView, which uses ProjectOptionalMixin without a project url kwarg."""

    def test_active_project_is_none_without_session(self):
        r = self.client.get(reverse("core:projects"))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["active_project"])

    def test_active_project_is_set_from_session(self):
        project = Project.objects.create(name="my-project")

        session = self.client.session
        session["active_project_id"] = project.pk
        session.save()

        r = self.client.get(reverse("core:projects"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["active_project"], project)

    def test_stale_project_in_session_is_ignored(self):
        project = Project.objects.create(name="to-be-deleted")

        session = self.client.session
        session["active_project_id"] = project.pk
        session.save()

        project.delete()

        r = self.client.get(reverse("core:projects"))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["active_project"])


class ProjectRequiredMixinTests(CoreLoginTestCase):
    """Exercised via EntityOverviewView, which uses ProjectRequiredMixin (url kwarg "project")."""

    def test_unknown_project_in_url_is_404(self):
        r = self.client.get(reverse("core:entities", kwargs={"project": 999999}))
        self.assertEqual(r.status_code, 404)

    def test_project_from_url_is_used_when_session_is_empty(self):
        project = Project.objects.create(name="p1")

        r = self.client.get(reverse("core:entities", kwargs={"project": project.pk}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["active_project"], project)

    def test_project_matching_session_is_allowed(self):
        project = Project.objects.create(name="p1")

        session = self.client.session
        session["active_project_id"] = project.pk
        session.save()

        r = self.client.get(reverse("core:entities", kwargs={"project": project.pk}))
        self.assertEqual(r.status_code, 200)

    def test_project_not_matching_session_raises_bad_request(self):
        project1 = Project.objects.create(name="p1")
        project2 = Project.objects.create(name="p2")

        session = self.client.session
        session["active_project_id"] = project1.pk
        session.save()

        r = self.client.get(reverse("core:entities", kwargs={"project": project2.pk}))
        self.assertEqual(r.status_code, 400)
