from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import ConfigOption
from squiggle_automation.testutils import random_password

User = get_user_model()


class ConfigOptionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:configoption-list"))
        self.assertEqual(r.status_code, 401)

    def test_list_configoptions(self):
        ConfigOption.objects.create(name="option-a")
        ConfigOption.objects.create(name="option-b")

        r = self.client.get(reverse("api:configoption-list"))
        self.assertEqual(r.status_code, 200)

        names = [o["name"] for o in r.data]
        self.assertIn("option-a", names)
        self.assertIn("option-b", names)

    def test_retrieve_configoption(self):
        option = ConfigOption.objects.create(name="option-retrieve", description="a description", sensitive=True)

        r = self.client.get(reverse("api:configoption-detail", args=[option.name]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "option-retrieve")
        self.assertEqual(r.data["description"], "a description")
        self.assertTrue(r.data["sensitive"])
        self.assertNotIn("id", r.data)

    def test_create_configoption(self):
        r = self.client.post(
            reverse("api:configoption-list"),
            {"name": "new-option", "description": "some help text", "sensitive": True},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)

        option = ConfigOption.objects.get(name="new-option")
        self.assertEqual(option.description, "some help text")
        self.assertTrue(option.sensitive)

    def test_update_configoption(self):
        option = ConfigOption.objects.create(name="to-update")

        r = self.client.patch(
            reverse("api:configoption-detail", args=[option.name]),
            {"sensitive": True},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        option.refresh_from_db()
        self.assertTrue(option.sensitive)

    def test_delete_configoption(self):
        option = ConfigOption.objects.create(name="to-delete")

        r = self.client.delete(reverse("api:configoption-detail", args=[option.name]))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(ConfigOption.objects.filter(pk=option.pk).exists())
