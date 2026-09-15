from unittest.mock import patch

from django.test import TestCase

from ..models import AutoApprovalRule, EntityType, Project
from ..models.autoapprovalrule import ACTION_APPROVE, OPERATOR_STRING_EQUALS_SENSITIVE
from ..tasks import run_auto_approval_rule

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}}}


class RunAutoApprovalRuleTaskTests(TestCase):
    """
    The task itself only looks the rule up and hands over to the model - what it then does to
    the waiting entities is covered by test_autoapprovalrule_model.py's RunOnWaitingEntitiesTests.
    """

    def setUp(self):
        self.entitytype = EntityType.objects.create(
            name="host", schema=SCHEMA, identifier_keys="address", approval_required=True
        )
        self.project = Project.objects.create(name="project-1")
        self.rule = AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

    def test_runs_the_rule(self):
        with patch.object(AutoApprovalRule, "run_on_waiting_entities") as mock_run:
            run_auto_approval_rule(self.rule.pk)

        mock_run.assert_called_once()

    def test_deleted_rule_is_silently_ignored(self):
        rule_id = self.rule.pk
        self.rule.delete()

        with patch.object(AutoApprovalRule, "run_on_waiting_entities") as mock_run:
            run_auto_approval_rule(rule_id)  # must not raise

        mock_run.assert_not_called()
