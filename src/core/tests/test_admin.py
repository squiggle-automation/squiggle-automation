from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from squiggle_automation.testutils import random_password

from ..models import ConfigOption, ConfigValue

User = get_user_model()


class ConfigValueAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", random_password())
        self.client.force_login(self.admin)

        self.sensitive_option = ConfigOption.objects.create(name="secret-opt", sensitive=True)
        self.normal_option = ConfigOption.objects.create(name="normal-opt", sensitive=False)

        self.sensitive_value = ConfigValue.objects.create(option=self.sensitive_option, value="topsecret123")
        self.normal_value = ConfigValue.objects.create(option=self.normal_option, value="plainvalue")

    def test_sensitive_value_not_shown_on_change_form(self):
        url = reverse("admin:core_configvalue_change", args=[self.sensitive_value.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

        content = r.content.decode()
        self.assertNotIn("topsecret123", content)
        self.assertIn("sensitive value, hidden", content)

    def test_normal_value_shown_on_change_form(self):
        url = reverse("admin:core_configvalue_change", args=[self.normal_value.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "plainvalue")

    def test_sensitive_value_cannot_be_changed_via_admin_post(self):
        # the "value" field is not part of the form for sensitive configvalues anymore
        url = reverse("admin:core_configvalue_change", args=[self.sensitive_value.pk])
        self.client.post(url, {"option": self.sensitive_option.pk, "_continue": "Save"})

        self.sensitive_value.refresh_from_db()
        self.assertEqual(self.sensitive_value.value, "topsecret123")
