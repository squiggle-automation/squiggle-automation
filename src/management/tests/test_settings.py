from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from squiggle_automation.testutils import random_password

User = get_user_model()


class SettingsViewTests(TestCase):
    def setUp(self):
        self.url = reverse("management:settings")

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_non_superuser_can_access(self):
        user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(user)

        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "management/settings.html")

    def test_non_superuser_does_not_see_user_management_links(self):
        user = User.objects.create_user("plain2", password=random_password())
        self.client.force_login(user)

        r = self.client.get(self.url)
        content = r.content.decode()
        self.assertNotIn(reverse("management:users"), content)
        self.assertNotIn(reverse("admin:index"), content)

    def test_non_superuser_sees_own_account_links(self):
        user = User.objects.create_user("plain3", password=random_password())
        self.client.force_login(user)

        r = self.client.get(self.url)
        content = r.content.decode()
        self.assertIn(reverse("management:password-change"), content)
        self.assertIn(reverse("management:apitoken"), content)

    def test_superuser_can_access(self):
        admin = User.objects.create_superuser("admin", "admin@example.com", random_password())
        self.client.force_login(admin)

        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "management/settings.html")

    def test_superuser_sees_user_management_links(self):
        admin = User.objects.create_superuser("admin2", "admin2@example.com", random_password())
        self.client.force_login(admin)

        r = self.client.get(self.url)
        content = r.content.decode()
        self.assertIn(reverse("management:users"), content)
        self.assertIn(reverse("admin:index"), content)

    def test_shows_app_version(self):
        user = User.objects.create_user("plain4", password=random_password())
        self.client.force_login(user)

        r = self.client.get(self.url)
        self.assertEqual(r.context["app_version"], settings.APP_VERSION)
        self.assertIn(settings.APP_VERSION, r.content.decode())
