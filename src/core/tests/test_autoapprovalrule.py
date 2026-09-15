import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from api.serializers import AutoApprovalRuleSerializer
from squiggle_automation.testutils import random_password

from ..models import AutoApprovalRule, EntityType, Project
from ..models.autoapprovalrule import ACTION_APPROVE, OPERATOR_STRING_EQUALS_SENSITIVE
from ..tasks import run_auto_approval_rule

User = get_user_model()

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class AutoApprovalRuleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plain", password=random_password())
        self.client.force_login(self.user)

        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.project = Project.objects.create(name="project-1")
        self.other_project = Project.objects.create(name="project-2")


class AutoApprovalRuleListViewTests(AutoApprovalRuleTestCase):
    def test_anonymous_redirected_to_login(self):
        self.client.logout()

        r = self.client.get(reverse("core:autoapprovalrules", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r.url)

    def test_lists_only_rules_of_the_current_project(self):
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

        r = self.client.get(reverse("core:autoapprovalrules", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

        names = [rule.name for rule in r.context["autoapprovalrules"]]
        self.assertEqual(names, ["own-rule"])

    def test_shows_json_matching_the_api_serializer(self):
        rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="rule-json",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.get(reverse("core:autoapprovalrules", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

        expected_json = json.dumps(AutoApprovalRuleSerializer(rule).data, indent=2)
        # rendered through django's autoescaping (correctly - schema content is user-controlled)
        self.assertContains(r, escape(expected_json))


class AutoApprovalRuleCreateViewTests(AutoApprovalRuleTestCase):
    def test_get_ok(self):
        r = self.client.get(reverse("core:autoapprovalrule-create", kwargs={"project": self.project.pk}))
        self.assertEqual(r.status_code, 200)

    def test_post_creates_rule_scoped_to_project(self):
        r = self.client.post(
            reverse("core:autoapprovalrule-create", kwargs={"project": self.project.pk}),
            {
                "entitytype": self.entitytype.pk,
                "name": "rule-1",
                "field": "address",
                "operator": OPERATOR_STRING_EQUALS_SENSITIVE,
                "values": "1.1.1.1",
                "action": ACTION_APPROVE,
            },
        )
        self.assertEqual(r.status_code, 302)

        rule = AutoApprovalRule.objects.get(name="rule-1")
        self.assertEqual(rule.project, self.project)
        self.assertEqual(rule.entitytype, self.entitytype)

    def test_post_field_not_in_schema_is_rejected(self):
        r = self.client.post(
            reverse("core:autoapprovalrule-create", kwargs={"project": self.project.pk}),
            {
                "entitytype": self.entitytype.pk,
                "name": "rule-1",
                "field": "not-a-schema-property",
                "operator": OPERATOR_STRING_EQUALS_SENSITIVE,
                "values": "1.1.1.1",
                "action": ACTION_APPROVE,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AutoApprovalRule.objects.filter(name="rule-1").exists())


class AutoApprovalRuleUpdateViewTests(AutoApprovalRuleTestCase):
    def setUp(self):
        super().setUp()
        self.rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="rule-1",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

    def test_get_ok(self):
        r = self.client.get(
            reverse("core:autoapprovalrule-update", kwargs={"project": self.project.pk, "pk": self.rule.pk})
        )
        self.assertEqual(r.status_code, 200)

    def test_rule_of_other_project_is_404(self):
        r = self.client.get(
            reverse("core:autoapprovalrule-update", kwargs={"project": self.other_project.pk, "pk": self.rule.pk})
        )
        self.assertEqual(r.status_code, 404)

    def test_post_updates_values(self):
        r = self.client.post(
            reverse("core:autoapprovalrule-update", kwargs={"project": self.project.pk, "pk": self.rule.pk}),
            {
                "entitytype": self.entitytype.pk,
                "name": "rule-1",
                "field": "address",
                "operator": OPERATOR_STRING_EQUALS_SENSITIVE,
                "values": "2.2.2.2",
                "action": ACTION_APPROVE,
            },
        )
        self.assertEqual(r.status_code, 302)

        self.rule.refresh_from_db()
        self.assertEqual(self.rule.values, "2.2.2.2")


class AutoApprovalRuleRunNowViewTests(AutoApprovalRuleTestCase):
    def setUp(self):
        super().setUp()
        self.rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="rule-1",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

    def test_post_queues_the_task_for_this_rule(self):
        with patch.object(run_auto_approval_rule, "delay") as mock_delay:
            r = self.client.post(
                reverse("core:autoapprovalrule-run", kwargs={"project": self.project.pk, "pk": self.rule.pk})
            )

        mock_delay.assert_called_once_with(self.rule.pk)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("core:autoapprovalrules", kwargs={"project": self.project.pk}))

    def test_rule_of_other_project_is_404(self):
        with patch.object(run_auto_approval_rule, "delay") as mock_delay:
            r = self.client.post(
                reverse("core:autoapprovalrule-run", kwargs={"project": self.other_project.pk, "pk": self.rule.pk})
            )

        self.assertEqual(r.status_code, 404)
        mock_delay.assert_not_called()


class AutoApprovalRuleDeleteViewTests(AutoApprovalRuleTestCase):
    def test_post_deletes_rule(self):
        rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="rule-1",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        r = self.client.post(
            reverse("core:autoapprovalrule-delete", kwargs={"project": self.project.pk, "pk": rule.pk})
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(AutoApprovalRule.objects.filter(pk=rule.pk).exists())
