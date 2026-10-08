from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AutoApprovalRule, EntityType, Project
from core.models.autoapprovalrule import (
    ACTION_APPROVE,
    OPERATOR_STRING_EQUALS_SENSITIVE,
)
from squiggle_automation.testutils import random_password

User = get_user_model()

VALID_SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class AutoApprovalRuleApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.entitytype = EntityType.objects.create(name="host", schema=VALID_SCHEMA, identifier_keys="address")
        self.project = Project.objects.create(name="project-1")
        self.other_project = Project.objects.create(name="project-2")

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(reverse("api:autoapprovalrule-list", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 401)

    def test_unknown_project_is_404(self):
        r = self.client.get(reverse("api:autoapprovalrule-list", kwargs={"project": 999999}))
        self.assertEqual(r.status_code, 404)

    def test_list_autoapprovalrules_scoped_to_the_project(self):
        AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="own-rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )
        AutoApprovalRule.objects.create(
            project=self.other_project,
            entitytype=self.entitytype,
            name="other-rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.get(reverse("api:autoapprovalrule-list", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

        names = [rule["name"] for rule in r.data]
        self.assertEqual(names, ["own-rule"])

    def test_retrieve_autoapprovalrule_references_entitytype_by_name(self):
        rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="rule-retrieve",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.get(
            reverse("api:autoapprovalrule-detail", kwargs={"project": self.project.pk, "name": rule.name})
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["entitytype"], self.entitytype.name)
        self.assertNotIn("project", r.data)
        self.assertNotIn("id", r.data)

    def test_retrieve_autoapprovalrule_of_other_project_is_404(self):
        rule = AutoApprovalRule.objects.create(
            project=self.other_project,
            entitytype=self.entitytype,
            name="rule-elsewhere",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.get(
            reverse("api:autoapprovalrule-detail", kwargs={"project": self.project.pk, "name": rule.name})
        )
        self.assertEqual(r.status_code, 404)

    def test_create_autoapprovalrule_is_scoped_to_the_url_project(self):
        r = self.client.post(
            reverse("api:autoapprovalrule-list", kwargs={"project": self.project.pk}),
            {
                "entitytype": self.entitytype.name,
                "name": "new-rule",
                "field": "address",
                "operator": OPERATOR_STRING_EQUALS_SENSITIVE,
                "values": "1.1.1.1",
                "action": ACTION_APPROVE,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)

        rule = AutoApprovalRule.objects.get(name="new-rule")
        self.assertEqual(rule.project, self.project)
        self.assertEqual(rule.entitytype, self.entitytype)

    def test_create_autoapprovalrule_with_field_not_in_schema_is_rejected(self):
        r = self.client.post(
            reverse("api:autoapprovalrule-list", kwargs={"project": self.project.pk}),
            {
                "entitytype": self.entitytype.name,
                "name": "bad-field-rule",
                "field": "not_defined",
                "operator": OPERATOR_STRING_EQUALS_SENSITIVE,
                "values": "1.1.1.1",
                "action": ACTION_APPROVE,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("field", r.data)
        self.assertFalse(AutoApprovalRule.objects.filter(name="bad-field-rule").exists())

    def test_create_autoapprovalrule_with_duplicate_name_is_rejected(self):
        AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="taken",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )
        payload = {
            "entitytype": self.entitytype.name,
            "name": "taken",
            "field": "address",
            "operator": OPERATOR_STRING_EQUALS_SENSITIVE,
            "values": "2.2.2.2",
            "action": ACTION_APPROVE,
        }

        r = self.client.post(
            reverse("api:autoapprovalrule-list", kwargs={"project": self.project.pk}), payload, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", r.data)

        # the same name in another project is fine
        r = self.client.post(
            reverse("api:autoapprovalrule-list", kwargs={"project": self.other_project.pk}), payload, format="json"
        )
        self.assertEqual(r.status_code, 201, r.content)

    def test_rename_autoapprovalrule_to_existing_name_is_rejected(self):
        for name in ("first", "second"):
            AutoApprovalRule.objects.create(
                project=self.project,
                entitytype=self.entitytype,
                name=name,
                field="address",
                operator=OPERATOR_STRING_EQUALS_SENSITIVE,
                values="1.1.1.1",
                action=ACTION_APPROVE,
            )

        r = self.client.patch(
            reverse("api:autoapprovalrule-detail", kwargs={"project": self.project.pk, "name": "second"}),
            {"name": "first"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", r.data)

    def test_update_autoapprovalrule(self):
        rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="to-update",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.patch(
            reverse("api:autoapprovalrule-detail", kwargs={"project": self.project.pk, "name": rule.name}),
            {"values": "2.2.2.2"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        rule.refresh_from_db()
        self.assertEqual(rule.values, "2.2.2.2")

    def test_delete_autoapprovalrule(self):
        rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="to-delete",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.delete(
            reverse("api:autoapprovalrule-detail", kwargs={"project": self.project.pk, "name": rule.name})
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(AutoApprovalRule.objects.filter(pk=rule.pk).exists())
