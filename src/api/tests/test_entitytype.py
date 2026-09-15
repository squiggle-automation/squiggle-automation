from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import EntityType
from squiggle_automation.testutils import random_password

User = get_user_model()

VALID_SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}, "comment": {"type": "string"}}}


class EntityTypeApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:entitytype-list"))
        self.assertEqual(r.status_code, 401)

    def test_list_entitytypes(self):
        EntityType.objects.create(name="type-a", schema=VALID_SCHEMA, identifier_keys="address")
        EntityType.objects.create(name="type-b", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.get(reverse("api:entitytype-list"))
        self.assertEqual(r.status_code, 200)

        names = [e["name"] for e in r.data]
        self.assertIn("type-a", names)
        self.assertIn("type-b", names)

    def test_retrieve_entitytype(self):
        entitytype = EntityType.objects.create(name="type-retrieve", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.get(reverse("api:entitytype-detail", args=[entitytype.name]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["name"], "type-retrieve")
        self.assertNotIn("id", r.data)

    def test_create_entitytype(self):
        r = self.client.post(
            reverse("api:entitytype-list"),
            {"name": "new-type", "schema": VALID_SCHEMA, "identifier_keys": "address"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(EntityType.objects.filter(name="new-type").exists())

    def test_create_entitytype_with_invalid_json_schema_is_rejected(self):
        r = self.client.post(
            reverse("api:entitytype-list"),
            {"name": "bad-schema-type", "schema": {"type": "not-a-real-type"}, "identifier_keys": "address"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("schema", r.data)
        self.assertFalse(EntityType.objects.filter(name="bad-schema-type").exists())

    def test_create_entitytype_with_identifier_key_not_in_schema_is_rejected(self):
        r = self.client.post(
            reverse("api:entitytype-list"),
            {"name": "bad-identifier-type", "schema": VALID_SCHEMA, "identifier_keys": "not_defined"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("identifier_keys", r.data)
        self.assertFalse(EntityType.objects.filter(name="bad-identifier-type").exists())

    def test_update_entitytype(self):
        entitytype = EntityType.objects.create(name="to-update", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.patch(
            reverse("api:entitytype-detail", args=[entitytype.name]),
            {"approval_required": True},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        entitytype.refresh_from_db()
        self.assertTrue(entitytype.approval_required)

    def test_update_entitytype_keeping_other_fields_still_validates(self):
        # partial update must still validate against the *combined* (existing + changed) state
        entitytype = EntityType.objects.create(name="to-partial-update", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.patch(
            reverse("api:entitytype-detail", args=[entitytype.name]),
            {"identifier_keys": "not_defined"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

        entitytype.refresh_from_db()
        self.assertEqual(entitytype.identifier_keys, "address")

    def test_delete_entitytype(self):
        entitytype = EntityType.objects.create(name="to-delete", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.delete(reverse("api:entitytype-detail", args=[entitytype.name]))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(EntityType.objects.filter(pk=entitytype.pk).exists())
