from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.authtoken.models import Token

from squiggle_automation.testutils import random_password

User = get_user_model()


class UserManagementTestCase(TestCase):
    """Base class that logs in as a superuser, as required by all user management views."""

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", random_password())
        self.client.force_login(self.admin)


class UserListViewTests(UserManagementTestCase):
    def test_lists_users_ordered_by_username(self):
        User.objects.create_user("charlie")
        User.objects.create_user("alice")
        User.objects.create_user("bob")

        r = self.client.get(reverse("management:users"))
        self.assertEqual(r.status_code, 200)

        usernames = [u.username for u in r.context["users"]]
        self.assertIn("alice", usernames)
        self.assertIn("bob", usernames)
        self.assertIn("charlie", usernames)
        self.assertEqual(usernames, sorted(usernames))

    def test_shows_api_token_column(self):
        with_token = User.objects.create_user("has-token")
        Token.objects.create(user=with_token)
        User.objects.create_user("no-token")

        r = self.client.get(reverse("management:users"))
        self.assertEqual(r.status_code, 200)

        users_by_username = {u.username: u for u in r.context["users"]}
        self.assertTrue(users_by_username["has-token"].auth_token)
        with self.assertRaises(Token.DoesNotExist):
            users_by_username["no-token"].auth_token

    def test_api_token_column_does_not_cause_n_plus_one_queries(self):
        for i in range(10):
            user = User.objects.create_user(f"bulk-user-{i}")
            if i % 2 == 0:
                Token.objects.create(user=user)

        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(reverse("management:users"))
        self.assertEqual(r.status_code, 200)
        # should not scale with the number of users (select_related avoids a query per row)
        self.assertLess(len(ctx.captured_queries), 10)

    def test_non_superuser_forbidden(self):
        self.client.logout()
        plain = User.objects.create_user("plain", password=random_password())
        self.client.force_login(plain)

        r = self.client.get(reverse("management:users"))
        self.assertEqual(r.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("management:users"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)


class UserCreateViewTests(UserManagementTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("management:user-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_user_with_hashed_password(self):
        password = random_password()
        r = self.client.post(
            reverse("management:user-create"),
            {
                "username": "newuser",
                "first_name": "New",
                "last_name": "User",
                "email": "new@example.com",
                "is_active": "on",
                "password1": password,
                "password2": password,
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("management:users"))

        user = User.objects.get(username="newuser")
        self.assertTrue(user.check_password(password))
        self.assertNotEqual(user.password, password)
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.is_superuser)

    def test_post_password_mismatch_is_rejected(self):
        password = random_password()
        r = self.client.post(
            reverse("management:user-create"),
            {
                "username": "newuser2",
                "password1": password,
                "password2": password + "different",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="newuser2").exists())


class UserUpdateViewTests(UserManagementTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("target", password=random_password())

    def test_get_ok(self):
        r = self.client.get(reverse("management:user-update", args=[self.user.pk]))
        self.assertEqual(r.status_code, 200)

    def test_post_updates_fields_without_touching_password(self):
        old_password_hash = self.user.password

        r = self.client.post(
            reverse("management:user-update", args=[self.user.pk]),
            {
                "username": "target",
                "first_name": "Changed",
                "last_name": "",
                "email": "changed@example.com",
                "is_active": "on",
                "is_superuser": "on",
            },
        )
        self.assertEqual(r.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Changed")
        self.assertEqual(self.user.email, "changed@example.com")
        self.assertTrue(self.user.is_superuser)
        self.assertEqual(self.user.password, old_password_hash)


class UserDeleteViewTests(UserManagementTestCase):
    def test_get_shows_confirmation(self):
        user = User.objects.create_user("todelete")

        r = self.client.get(reverse("management:user-delete", args=[user.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "todelete")

    def test_post_deletes_user(self):
        user = User.objects.create_user("todelete2")

        r = self.client.post(reverse("management:user-delete", args=[user.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())


class UserPasswordResetViewTests(UserManagementTestCase):
    def setUp(self):
        super().setUp()
        self.target = User.objects.create_user("target2", password=random_password())

    def test_get_renders_target_username(self):
        r = self.client.get(reverse("management:user-password-reset", args=[self.target.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "target2")

    def test_post_changes_password(self):
        new_password = random_password()
        r = self.client.post(
            reverse("management:user-password-reset", args=[self.target.pk]),
            {"new_password1": new_password, "new_password2": new_password},
        )
        self.assertEqual(r.status_code, 302)

        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(new_password))

    def test_admin_session_still_valid_after_resetting_someone_elses_password(self):
        new_password = random_password()
        self.client.post(
            reverse("management:user-password-reset", args=[self.target.pk]),
            {"new_password1": new_password, "new_password2": new_password},
        )

        r = self.client.get(reverse("management:users"))
        self.assertEqual(r.status_code, 200)
