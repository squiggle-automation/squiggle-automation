from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from squiggle_automation.testutils import random_password

User = get_user_model()


class PasswordChangeViewTests(TestCase):
    def setUp(self):
        self.old_password = random_password()
        self.user = User.objects.create_user("alice", password=self.old_password)
        self.client.force_login(self.user)
        self.url = reverse("management:password-change")

    def test_get_ok(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)

    def test_post_changes_own_password_and_redirects(self):
        new_password = random_password()
        r = self.client.post(
            self.url,
            {"old_password": self.old_password, "new_password1": new_password, "new_password2": new_password},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:start"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_wrong_old_password_is_rejected(self):
        new_password = random_password()
        r = self.client.post(
            self.url,
            {
                "old_password": self.old_password + "wrong",
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(r.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_non_superuser_can_change_own_password(self):
        # unlike the other management views, this one is not restricted to superusers
        self.assertFalse(self.user.is_superuser)

        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
