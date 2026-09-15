import json

from django.contrib.auth import get_user_model
from django.forms import PasswordInput
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from api.serializers import ConfigOptionSerializer
from squiggle_automation.testutils import random_password

from ..models import ConfigOption, ConfigValue

User = get_user_model()


class ConfigOptionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)


class ConfigOptionListViewTests(ConfigOptionTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:configoptions"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_configoptions(self):
        ConfigOption.objects.create(name="opt-b")
        ConfigOption.objects.create(name="opt-a")

        r = self.client.get(reverse("core:configoptions"))
        self.assertEqual(r.status_code, 200)

        names = [c.name for c in r.context["configoptions"]]
        self.assertEqual(names, ["opt-a", "opt-b"])

    def test_shows_json_matching_the_api_serializer(self):
        option = ConfigOption.objects.create(name="opt-json", description="a description", sensitive=True)

        r = self.client.get(reverse("core:configoptions"))
        self.assertEqual(r.status_code, 200)

        expected_json = json.dumps(ConfigOptionSerializer(option).data, indent=2)
        self.assertContains(r, escape(expected_json))
        self.assertContains(r, f'data-bs-target="#configoption-json-{option.pk}"')
        self.assertContains(r, f'id="configoption-json-{option.pk}-content"')

    def test_json_modal_notes_that_config_values_are_not_included(self):
        option = ConfigOption.objects.create(name="opt-json-note")

        r = self.client.get(reverse("core:configoptions"))

        self.assertContains(r, "Config values are not included here")


class ConfigOptionCreateViewTests(ConfigOptionTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:configoption-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_configoption(self):
        r = self.client.post(
            reverse("core:configoption-create"),
            {"name": "my-option", "description": "some help text", "sensitive": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:configoptions"))

        option = ConfigOption.objects.get(name="my-option")
        self.assertEqual(option.description, "some help text")
        self.assertFalse(option.sensitive)


class ConfigOptionUpdateViewTests(ConfigOptionTestCase):
    def setUp(self):
        super().setUp()
        self.option = ConfigOption.objects.create(name="my-option", description="desc")

    def test_get_shows_value_form(self):
        r = self.client.get(reverse("core:configoption-update", args=[self.option.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("value_form", r.context)
        # help text on the value field is taken from the configoption's description
        self.assertEqual(r.context["value_form"].fields["value"].help_text, "desc")

    def test_post_updates_configoption_fields(self):
        r = self.client.post(
            reverse("core:configoption-update", args=[self.option.pk]),
            {"name": "renamed", "description": "new desc", "sensitive": "", "value-value": ""},
        )
        self.assertEqual(r.status_code, 302)

        self.option.refresh_from_db()
        self.assertEqual(self.option.name, "renamed")
        self.assertEqual(self.option.description, "new desc")

    def test_post_sets_global_default_value(self):
        r = self.client.post(
            reverse("core:configoption-update", args=[self.option.pk]),
            {"name": "my-option", "description": "desc", "sensitive": "", "value-value": "hello"},
        )
        self.assertEqual(r.status_code, 302)

        value = ConfigValue.objects.get(option=self.option, executor__isnull=True)
        self.assertEqual(value.value, "hello")

    def test_post_empty_value_deletes_existing_default_value(self):
        ConfigValue.objects.create(option=self.option, executor=None, value="initial")

        r = self.client.post(
            reverse("core:configoption-update", args=[self.option.pk]),
            {"name": "my-option", "description": "desc", "sensitive": "", "value-value": ""},
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ConfigValue.objects.filter(option=self.option, executor__isnull=True).exists())

    def test_post_invalid_configoption_form_is_rerendered(self):
        other = ConfigOption.objects.create(name="already-taken")

        r = self.client.post(
            reverse("core:configoption-update", args=[self.option.pk]),
            {"name": other.name, "description": "desc", "sensitive": "", "value-value": ""},
        )
        self.assertEqual(r.status_code, 200)

        self.option.refresh_from_db()
        self.assertEqual(self.option.name, "my-option")

    def test_sensitive_option_uses_password_widget_and_clear_checkbox(self):
        sensitive_option = ConfigOption.objects.create(name="secret-option", sensitive=True)

        r = self.client.get(reverse("core:configoption-update", args=[sensitive_option.pk]))
        self.assertEqual(r.status_code, 200)

        value_form = r.context["value_form"]
        self.assertIsInstance(value_form.fields["value"].widget, PasswordInput)
        self.assertIn("clear", value_form.fields)

    def test_sensitive_option_clear_checkbox_deletes_value(self):
        sensitive_option = ConfigOption.objects.create(name="secret-option", sensitive=True)
        ConfigValue.objects.create(option=sensitive_option, executor=None, value="topsecret")

        r = self.client.post(
            reverse("core:configoption-update", args=[sensitive_option.pk]),
            {
                "name": "secret-option",
                "description": "",
                "sensitive": "on",
                "value-value": "",
                "value-clear": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ConfigValue.objects.filter(option=sensitive_option, executor__isnull=True).exists())

    def test_sensitive_option_blank_value_keeps_old_value(self):
        sensitive_option = ConfigOption.objects.create(name="secret-option", sensitive=True)
        ConfigValue.objects.create(option=sensitive_option, executor=None, value="topsecret")

        # posting without a new value and without "clear" should keep the old value (sensitive values are
        # never rendered back into the form, so a blank submission must not wipe them out)
        r = self.client.post(
            reverse("core:configoption-update", args=[sensitive_option.pk]),
            {
                "name": "secret-option",
                "description": "",
                "sensitive": "on",
                "value-value": "",
            },
        )
        self.assertEqual(r.status_code, 302)

        value = ConfigValue.objects.get(option=sensitive_option, executor__isnull=True)
        self.assertEqual(value.value, "topsecret")


class ConfigOptionDeleteViewTests(ConfigOptionTestCase):
    def test_get_shows_confirmation(self):
        option = ConfigOption.objects.create(name="to-delete")

        r = self.client.get(reverse("core:configoption-delete", args=[option.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "to-delete")

    def test_post_deletes_configoption(self):
        option = ConfigOption.objects.create(name="to-delete2")

        r = self.client.post(reverse("core:configoption-delete", args=[option.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(ConfigOption.objects.filter(pk=option.pk).exists())
