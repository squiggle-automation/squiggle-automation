from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from squiggle_automation.testutils import random_password

from ..models import Entity, EntityType, Project

User = get_user_model()


class ProjectTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)


class ProjectListViewTests(ProjectTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:projects"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_projects_with_switch_forms(self):
        Project.objects.create(name="alpha")
        Project.objects.create(name="beta")

        r = self.client.get(reverse("core:projects"))
        self.assertEqual(r.status_code, 200)

        names = [p.name for p in r.context["projects"]]
        self.assertEqual(names, ["alpha", "beta"])
        for p in r.context["projects"]:
            self.assertEqual(p.switch_form.initial["project"], p.pk)


class ProjectCreateViewTests(ProjectTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:project-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_project_and_redirects_to_list(self):
        r = self.client.post(reverse("core:project-create"), {"name": "new-project", "run_executors": "on"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:projects"))

        project = Project.objects.get(name="new-project")
        self.assertTrue(project.run_executors)

    def test_post_creates_project_index_for_existing_entitytypes(self):
        EntityType.objects.create(
            name="host",
            schema={"type": "object", "properties": {"address": {"type": "string"}}},
            identifier_keys="address",
        )

        r = self.client.post(reverse("core:project-create"), {"name": "new-project2"})
        self.assertEqual(r.status_code, 302)

        project = Project.objects.get(name="new-project2")
        entitytype = EntityType.objects.get(name="host")

        # the unique index created for this project/entitytype combination allows upsert_entity to work
        _, created = Entity.objects.upsert_entity(entitytype, project, {"address": "1.2.3.4"})
        self.assertTrue(created)


class ProjectUpdateViewTests(ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name="original")

    def test_get_ok(self):
        r = self.client.get(reverse("core:project-update", args=[self.project.pk]))
        self.assertEqual(r.status_code, 200)

    def test_post_updates_project(self):
        r = self.client.post(
            reverse("core:project-update", args=[self.project.pk]),
            {"name": "renamed", "run_executors": ""},
        )
        self.assertEqual(r.status_code, 302)

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "renamed")
        self.assertFalse(self.project.run_executors)


class ProjectDeleteViewTests(ProjectTestCase):
    def test_get_shows_confirmation(self):
        project = Project.objects.create(name="to-delete")

        r = self.client.get(reverse("core:project-delete", args=[project.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "to-delete")

    def test_post_deletes_project(self):
        project = Project.objects.create(name="to-delete2")

        r = self.client.post(reverse("core:project-delete", args=[project.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())


class ProjectSwitchViewTests(ProjectTestCase):
    def test_post_stores_project_in_session_and_redirects_to_entities(self):
        project = Project.objects.create(name="switchable")

        r = self.client.post(reverse("core:project-switch"), {"project": project.pk})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:entities", kwargs={"project": project.pk}))
        self.assertEqual(self.client.session["active_project_id"], project.pk)

    def test_post_unknown_project_is_404(self):
        r = self.client.post(reverse("core:project-switch"), {"project": 999999})
        self.assertEqual(r.status_code, 404)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.post(reverse("core:project-switch"), {"project": 1})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)
