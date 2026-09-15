import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from api.serializers import EntityTypeSerializer
from squiggle_automation.testutils import random_password

from ..models import Entity, EntityType, Project

User = get_user_model()

VALID_SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}, "comment": {"type": "string"}}}


class EntityTypeTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)


class EntityTypeListViewTests(EntityTypeTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:entitytypes"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_entitytypes(self):
        EntityType.objects.create(name="t-b", schema=VALID_SCHEMA, identifier_keys="address")
        EntityType.objects.create(name="t-a", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.get(reverse("core:entitytypes"))
        self.assertEqual(r.status_code, 200)

        names = [e.name for e in r.context["entitytypes"]]
        self.assertEqual(names, ["t-a", "t-b"])

    def test_shows_json_matching_the_api_serializer(self):
        entitytype = EntityType.objects.create(
            name="t-json", schema=VALID_SCHEMA, identifier_keys="address, comment", approval_required=True
        )

        r = self.client.get(reverse("core:entitytypes"))
        self.assertEqual(r.status_code, 200)

        expected_json = json.dumps(EntityTypeSerializer(entitytype).data, indent=2)
        # rendered through django's autoescaping (correctly - schema content is user-controlled)
        self.assertContains(r, escape(expected_json))

    def test_copy_to_clipboard_button_targets_the_json_element(self):
        entitytype = EntityType.objects.create(name="t-copy", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.get(reverse("core:entitytypes"))

        self.assertContains(r, f'id="entitytype-json-{entitytype.pk}-content"')
        self.assertContains(r, f'data-clipboard-target="entitytype-json-{entitytype.pk}-content"')
        self.assertContains(r, f'data-bs-target="#entitytype-json-{entitytype.pk}"')


class EntityTypeCreateViewTests(EntityTypeTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:entitytype-create"))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_entitytype(self):
        r = self.client.post(
            reverse("core:entitytype-create"),
            {
                "name": "host",
                "schema": '{"type": "object", "properties": {"address": {"type": "string"}}}',
                "identifier_keys": "address",
                "approval_required": "",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:entitytypes"))

        entitytype = EntityType.objects.get(name="host")
        self.assertEqual(entitytype.identifier_keys, "address")
        self.assertFalse(entitytype.approval_required)

    def test_post_invalid_json_schema_is_rejected(self):
        r = self.client.post(
            reverse("core:entitytype-create"),
            {
                "name": "host",
                "schema": '{"type": "not-a-real-type"}',
                "identifier_keys": "address",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EntityType.objects.filter(name="host").exists())

    def test_post_identifier_key_not_in_schema_is_rejected(self):
        r = self.client.post(
            reverse("core:entitytype-create"),
            {
                "name": "host",
                "schema": '{"type": "object", "properties": {"address": {"type": "string"}}}',
                "identifier_keys": "not_a_defined_property",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(EntityType.objects.filter(name="host").exists())


class EntityTypeUpdateViewTests(EntityTypeTestCase):
    def setUp(self):
        super().setUp()
        self.entitytype = EntityType.objects.create(name="host", schema=VALID_SCHEMA, identifier_keys="address")

    def test_get_ok(self):
        r = self.client.get(reverse("core:entitytype-update", args=[self.entitytype.pk]))
        self.assertEqual(r.status_code, 200)

    def test_post_updates_entitytype(self):
        r = self.client.post(
            reverse("core:entitytype-update", args=[self.entitytype.pk]),
            {
                "name": "host",
                "schema": '{"type": "object", "properties": {"address": {"type": "string"}, "comment": {"type": "string"}}}',
                "identifier_keys": "address, comment",
                "approval_required": "on",
            },
        )
        self.assertEqual(r.status_code, 302)

        self.entitytype.refresh_from_db()
        self.assertEqual(self.entitytype.identifier_keys, "address, comment")
        self.assertTrue(self.entitytype.approval_required)


class EntityTypeDeleteViewTests(EntityTypeTestCase):
    def test_get_shows_confirmation(self):
        entitytype = EntityType.objects.create(name="to-delete", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.get(reverse("core:entitytype-delete", args=[entitytype.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "to-delete")

    def test_post_deletes_entitytype(self):
        entitytype = EntityType.objects.create(name="to-delete2", schema=VALID_SCHEMA, identifier_keys="address")

        r = self.client.post(reverse("core:entitytype-delete", args=[entitytype.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(EntityType.objects.filter(pk=entitytype.pk).exists())


class EntityTypeModelTests(TestCase):
    def test_identifier_keys_list_strips_whitespace(self):
        entitytype = EntityType(name="host", schema=VALID_SCHEMA, identifier_keys="address, comment")
        self.assertEqual(entitytype.identifier_keys_list, ["address", "comment"])

    def test_schema_keys_puts_identifier_and_required_keys_first(self):
        entitytype = EntityType(
            name="service",
            schema={
                "type": "object",
                "required": ["address", "port"],
                "properties": {
                    "service": {"type": "string"},
                    "port": {"type": "number"},
                    "address": {"type": "string"},
                },
            },
            identifier_keys="port",
        )

        # the identifier key first, then the remaining required one, then the rest
        self.assertEqual(entitytype.schema_keys_list, ["port", "address", "service"])

    def test_schema_keys_is_empty_without_properties(self):
        entitytype = EntityType(name="host", schema={"type": "object"}, identifier_keys="address")
        self.assertEqual(entitytype.schema_keys_list, [])

    def test_schema_key_type_returns_the_type_of_a_key(self):
        entitytype = EntityType(
            name="service",
            schema={
                "type": "object",
                "properties": {"address": {"type": "string"}, "port": {"type": "number"}},
            },
            identifier_keys="address",
        )

        self.assertEqual(entitytype.schema_key_type("address"), "string")
        self.assertEqual(entitytype.schema_key_type("port"), "number")

    def test_schema_key_type_is_none_when_it_is_not_a_single_type(self):
        entitytype = EntityType(
            name="service",
            schema={
                "type": "object",
                "properties": {
                    "unknown": {"type": ["string", "null"]},  # more than one type
                    "untyped": {"description": "no type at all"},
                    "broken": "not-an-object",
                },
            },
            identifier_keys="untyped",
        )

        self.assertIsNone(entitytype.schema_key_type("unknown"))
        self.assertIsNone(entitytype.schema_key_type("untyped"))
        self.assertIsNone(entitytype.schema_key_type("broken"))
        self.assertIsNone(entitytype.schema_key_type("not_in_the_schema"))

    def test_schema_key_type_is_none_without_properties(self):
        entitytype = EntityType(name="host", schema={"type": "object"}, identifier_keys="address")

        self.assertIsNone(entitytype.schema_key_type("address"))

    def test_clean_accepts_valid_schema_and_identifier_keys(self):
        entitytype = EntityType(name="host", schema=VALID_SCHEMA, identifier_keys="address")
        entitytype.clean()  # should not raise

    def test_clean_rejects_invalid_json_schema(self):
        entitytype = EntityType(name="host", schema={"type": "not-a-real-type"}, identifier_keys="address")
        with self.assertRaises(ValidationError):
            entitytype.clean()

    def test_clean_rejects_identifier_key_not_defined_in_schema(self):
        entitytype = EntityType(name="host", schema=VALID_SCHEMA, identifier_keys="not_defined")
        with self.assertRaises(ValidationError):
            entitytype.clean()

    def test_clean_rejects_schema_without_properties(self):
        # a schema without "properties" is a valid JSON schema, but can never define any identifier keys
        entitytype = EntityType(name="host", schema={"type": "object"}, identifier_keys="address")
        with self.assertRaises(ValidationError):
            entitytype.clean()

    def test_save_creates_index_for_entitytype_added_after_project_exists(self):
        # regression test: a project that already existed before this entitytype was created must still
        # get a working unique index for this entitytype/project combination
        project = Project.objects.create(name="existing-project")
        entitytype = EntityType.objects.create(
            name="host",
            schema={"type": "object", "properties": {"address": {"type": "string"}}},
            identifier_keys="address",
        )

        # if the index was not created, this raises django.db.utils.ProgrammingError
        _, created = Entity.objects.upsert_entity(entitytype, project, {"address": "1.2.3.4"})
        self.assertTrue(created)
