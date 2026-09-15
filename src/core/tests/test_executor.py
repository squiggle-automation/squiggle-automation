import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.forms import PasswordInput
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from api.serializers import ExecutorSerializer
from squiggle_automation.testutils import random_password

from ..models import ConfigOption, ConfigValue, Container, Executor, Project
from ..tasks import run_executor_all_entities

User = get_user_model()


class ExecutorTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)
        self.container = Container.objects.create(name="container", image="image")


class ExecutorListViewTests(ExecutorTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:executors"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_executors(self):
        Executor.objects.create(name="e-b", container=self.container)
        Executor.objects.create(name="e-a", container=self.container)

        r = self.client.get(reverse("core:executors"))
        self.assertEqual(r.status_code, 200)

        names = [e.name for e in r.context["executors"]]
        self.assertEqual(names, ["e-a", "e-b"])

    def test_shows_json_matching_the_api_serializer(self):
        executor = Executor.objects.create(name="e-json", container=self.container)

        r = self.client.get(reverse("core:executors"))
        self.assertEqual(r.status_code, 200)

        expected_json = json.dumps(ExecutorSerializer(executor).data, indent=2)
        self.assertContains(r, escape(expected_json))
        self.assertContains(r, f'data-bs-target="#executor-json-{executor.pk}"')
        self.assertContains(r, f'id="executor-json-{executor.pk}-content"')

    def test_json_modal_notes_that_config_values_are_not_included(self):
        executor = Executor.objects.create(name="e-json-note", container=self.container)

        r = self.client.get(reverse("core:executors"))

        self.assertContains(r, "Config values are not included here")


class ExecutorCreateViewTests(ExecutorTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:executor-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_executor_and_redirects_to_list(self):
        r = self.client.post(
            reverse("core:executor-create"),
            {
                "name": "my-executor",
                "container": self.container.pk,
                "max_entities": 50,
                "max_entities_timeout": 10,
                "enabled": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:executors"))

        executor = Executor.objects.get(name="my-executor")
        self.assertEqual(executor.container, self.container)
        self.assertEqual(executor.max_entities, 50)


class ExecutorUpdateViewTests(ExecutorTestCase):
    def setUp(self):
        super().setUp()
        self.executor = Executor.objects.create(name="original", container=self.container)

    def test_get_ok(self):
        r = self.client.get(reverse("core:executor-update", args=[self.executor.pk]))
        self.assertEqual(r.status_code, 200)

    def test_post_updates_executor(self):
        r = self.client.post(
            reverse("core:executor-update", args=[self.executor.pk]),
            {
                "name": "renamed",
                "container": self.container.pk,
                "max_entities": 100,
                "max_entities_timeout": 5,
            },
        )
        self.assertEqual(r.status_code, 302)

        self.executor.refresh_from_db()
        self.assertEqual(self.executor.name, "renamed")
        # "enabled" was not sent, checkbox behavior means it becomes False
        self.assertFalse(self.executor.enabled)


class ExecutorConfigViewTests(ExecutorTestCase):
    def setUp(self):
        super().setUp()
        self.executor = Executor.objects.create(name="my-executor", container=self.container)
        self.option = ConfigOption.objects.create(name="plain-option", description="help for plain option")
        self.sensitive_option = ConfigOption.objects.create(name="secret-option", sensitive=True)
        self.container.configoptions.set([self.option, self.sensitive_option])

    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:executor-config", args=[self.executor.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_get_builds_one_form_per_configoption_of_the_container(self):
        r = self.client.get(reverse("core:executor-config", args=[self.executor.pk]))
        self.assertEqual(r.status_code, 200)

        value_forms = r.context["value_forms"]
        self.assertEqual(len(value_forms), 2)

        forms_by_option = {f.configoption: f for f in value_forms}
        self.assertEqual(forms_by_option[self.option].fields["value"].help_text, "help for plain option")
        self.assertIsInstance(forms_by_option[self.sensitive_option].fields["value"].widget, PasswordInput)

    def test_get_with_no_configoptions_on_container(self):
        empty_container = Container.objects.create(name="empty", image="image")
        executor = Executor.objects.create(name="no-config-executor", container=empty_container)

        r = self.client.get(reverse("core:executor-config", args=[executor.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["value_forms"], [])

    def test_post_saves_value_scoped_to_this_executor(self):
        r = self.client.post(
            reverse("core:executor-config", args=[self.executor.pk]),
            {
                f"value-{self.option.pk}-value": "executor-specific-value",
                f"value-{self.sensitive_option.pk}-value": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:executors"))

        value = ConfigValue.objects.get(option=self.option, executor=self.executor)
        self.assertEqual(value.value, "executor-specific-value")

    def test_does_not_touch_global_default_value(self):
        ConfigValue.objects.create(option=self.option, executor=None, value="global-default")

        self.client.post(
            reverse("core:executor-config", args=[self.executor.pk]),
            {
                f"value-{self.option.pk}-value": "executor-specific-value",
                f"value-{self.sensitive_option.pk}-value": "",
            },
        )

        default_value = ConfigValue.objects.get(option=self.option, executor__isnull=True)
        self.assertEqual(default_value.value, "global-default")

    def test_post_sensitive_clear_deletes_executor_value(self):
        ConfigValue.objects.create(option=self.sensitive_option, executor=self.executor, value="topsecret")

        r = self.client.post(
            reverse("core:executor-config", args=[self.executor.pk]),
            {
                f"value-{self.option.pk}-value": "",
                f"value-{self.sensitive_option.pk}-value": "",
                f"value-{self.sensitive_option.pk}-clear": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ConfigValue.objects.filter(option=self.sensitive_option, executor=self.executor).exists())


class ExecutorRunAllEntitiesViewTests(ExecutorTestCase):
    def setUp(self):
        super().setUp()
        self.executor = Executor.objects.create(name="my-executor", container=self.container)
        self.project = Project.objects.create(name="project-1")

        session = self.client.session
        session["active_project_id"] = self.project.pk
        session.save()

    def test_post_queues_the_task_for_this_executor(self):
        with patch.object(run_executor_all_entities, "delay") as mock_delay:
            r = self.client.post(reverse("core:executor-run-all-entities", args=[self.executor.pk]))

        mock_delay.assert_called_once_with(self.executor.pk, self.project.pk)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:executors"))

    def test_post_for_disabled_executor_shows_error_and_does_not_queue(self):
        self.executor.enabled = False
        self.executor.save()

        with patch.object(run_executor_all_entities, "delay") as mock_delay:
            r = self.client.post(reverse("core:executor-run-all-entities", args=[self.executor.pk]))

        mock_delay.assert_not_called()
        self.assertEqual(r.status_code, 302)

        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("disabled" in str(m) for m in messages))

    def test_post_without_active_project_shows_error_and_does_not_queue(self):
        session = self.client.session
        del session["active_project_id"]
        session.save()

        with patch.object(run_executor_all_entities, "delay") as mock_delay:
            r = self.client.post(reverse("core:executor-run-all-entities", args=[self.executor.pk]))

        mock_delay.assert_not_called()
        self.assertEqual(r.status_code, 302)

        messages = list(get_messages(r.wsgi_request))
        self.assertTrue(any("No projet opened" in str(m) for m in messages))

    def test_unknown_executor_is_404(self):
        r = self.client.post(reverse("core:executor-run-all-entities", args=[self.executor.pk + 1000]))
        self.assertEqual(r.status_code, 404)


class ExecutorDeleteViewTests(ExecutorTestCase):
    def test_get_shows_confirmation(self):
        executor = Executor.objects.create(name="to-delete", container=self.container)

        r = self.client.get(reverse("core:executor-delete", args=[executor.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "to-delete")

    def test_post_deletes_executor(self):
        executor = Executor.objects.create(name="to-delete2", container=self.container)

        r = self.client.post(reverse("core:executor-delete", args=[executor.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Executor.objects.filter(pk=executor.pk).exists())
