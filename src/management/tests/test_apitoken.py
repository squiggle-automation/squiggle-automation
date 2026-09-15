from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token

from core.models import Project
from squiggle_automation.testutils import random_password

User = get_user_model()


class ApiTokenViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("management:apitoken"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_shows_no_token_message_when_unset(self):
        r = self.client.get(reverse("management:apitoken"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "do not have an API token")

    def test_shows_masked_token_when_set(self):
        token = Token.objects.create(user=self.user)

        r = self.client.get(reverse("management:apitoken"))
        self.assertEqual(r.status_code, 200)
        content = r.content.decode()
        self.assertNotIn(token.key, content)
        self.assertIn(token.key[:3], content)
        self.assertIn(token.key[-3:], content)

    def test_create_creates_token_and_shows_it_once_via_message(self):
        r = self.client.post(reverse("management:apitoken-create"), follow=True)
        self.assertEqual(r.status_code, 200)

        token = Token.objects.get(user=self.user)
        self.assertContains(r, token.key)

    def test_create_when_already_exists_is_rejected(self):
        existing = Token.objects.create(user=self.user)

        r = self.client.post(reverse("management:apitoken-create"), follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "already have an API token")

        # unchanged
        self.assertEqual(Token.objects.get(user=self.user).key, existing.key)
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

    def test_create_does_not_leak_key_in_redirect_url(self):
        r = self.client.post(reverse("management:apitoken-create"))
        self.assertEqual(r.status_code, 302)
        token = Token.objects.get(user=self.user)
        self.assertNotIn(token.key, r.url)

    def test_delete_removes_token(self):
        Token.objects.create(user=self.user)

        r = self.client.post(reverse("management:apitoken-delete"), follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_delete_only_affects_own_token(self):
        other_user = User.objects.create_user("other", password=random_password())
        other_token = Token.objects.create(user=other_user)

        self.client.post(reverse("management:apitoken-delete"))

        self.assertTrue(Token.objects.filter(pk=other_token.pk).exists())

    def test_token_authenticates_api_requests(self):
        # end-to-end: a token created via this view actually works for api auth
        token = Token.objects.create(user=self.user)
        Project.objects.create(name="proj")

        api_client = Client()
        r = api_client.get("/api/v1/projects/", HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(r.status_code, 200)
