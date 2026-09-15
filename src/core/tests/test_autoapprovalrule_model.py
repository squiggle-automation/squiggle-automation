from django.core.exceptions import ValidationError
from django.test import TestCase

from ..models import AutoApprovalRule, Entity, EntityType, Event, Project
from ..models.autoapprovalrule import (
    ACTION_APPROVE,
    ACTION_DECLINE,
    OPERATOR_IP_IN_RANGE,
    OPERATOR_IS_SUBDOMAIN,
    OPERATOR_REGEX,
    OPERATOR_STRING_EQUALS_INSENSITIVE,
    OPERATOR_STRING_EQUALS_SENSITIVE,
    evaluate_all_auto_approval_rules_on_entity,
)

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}, "comment": {"type": "string"}}}


class AutoApprovalRuleTestCase(TestCase):
    def setUp(self):
        # entitytype must exist before the project so that the upsert index gets created for it (see EntityType.save())
        self.entitytype = EntityType.objects.create(
            name="host", schema=SCHEMA, identifier_keys="address", approval_required=True
        )
        self.other_entitytype = EntityType.objects.create(
            name="other", schema=SCHEMA, identifier_keys="address", approval_required=True
        )
        self.project = Project.objects.create(name="project-1")

    def make_rule(self, **kwargs):
        kwargs.setdefault("project", self.project)
        kwargs.setdefault("entitytype", self.entitytype)
        kwargs.setdefault("name", "rule")
        return AutoApprovalRule.objects.create(**kwargs)


class ValuesListTests(AutoApprovalRuleTestCase):
    def test_splits_values_on_newlines_and_ignores_blank_lines(self):
        rule = self.make_rule(
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1\n\n2.2.2.2\n ",
            action=ACTION_APPROVE,
        )
        self.assertEqual(rule.values_list, ["1.1.1.1", "2.2.2.2"])


class MatchesTests(AutoApprovalRuleTestCase):
    def test_string_equals_matches_exact_value(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "1.1.1.1"}))
        self.assertFalse(rule.matches({"address": "1.1.1.2"}))

    def test_string_equals_any_of_multiple_values_matches(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1\n2.2.2.2", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "2.2.2.2"}))
        self.assertFalse(rule.matches({"address": "3.3.3.3"}))

    def test_string_equals_sensitive_rejects_different_case(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="Example.com", action=ACTION_APPROVE
        )
        self.assertFalse(rule.matches({"address": "example.com"}))

    def test_string_equals_insensitive_matches_regardless_of_case(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_INSENSITIVE, values="Example.com", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "example.com"}))
        self.assertTrue(rule.matches({"address": "EXAMPLE.COM"}))
        self.assertFalse(rule.matches({"address": "other.com"}))

    def test_regex_matches_anywhere_in_string(self):
        rule = self.make_rule(field="address", operator=OPERATOR_REGEX, values="^10\\.", action=ACTION_APPROVE)
        self.assertTrue(rule.matches({"address": "10.0.0.1"}))
        self.assertFalse(rule.matches({"address": "192.168.0.1"}))

    def test_regex_with_invalid_pattern_does_not_match_and_does_not_raise(self):
        rule = self.make_rule(field="address", operator=OPERATOR_REGEX, values="(", action=ACTION_APPROVE)
        self.assertFalse(rule.matches({"address": "10.0.0.1"}))

    def test_ip_in_range_matches_cidr(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IP_IN_RANGE, values="10.0.0.0/8", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "10.1.2.3"}))
        self.assertFalse(rule.matches({"address": "192.168.0.1"}))

    def test_ip_in_range_with_invalid_ip_does_not_match_and_does_not_raise(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IP_IN_RANGE, values="10.0.0.0/8", action=ACTION_APPROVE
        )
        self.assertFalse(rule.matches({"address": "not-an-ip"}))

    def test_is_subdomain_matches_a_direct_subdomain(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IS_SUBDOMAIN, values="example.com", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "sub.example.com"}))

    def test_is_subdomain_matches_a_nested_subdomain(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IS_SUBDOMAIN, values="example.com", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "a.b.example.com"}))

    def test_is_subdomain_rejects_the_domain_itself(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IS_SUBDOMAIN, values="example.com", action=ACTION_APPROVE
        )
        self.assertFalse(rule.matches({"address": "example.com"}))

    def test_is_subdomain_rejects_an_unrelated_domain(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IS_SUBDOMAIN, values="example.com", action=ACTION_APPROVE
        )
        self.assertFalse(rule.matches({"address": "notexample.com"}))
        self.assertFalse(rule.matches({"address": "example.org"}))

    def test_is_subdomain_is_case_insensitive(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IS_SUBDOMAIN, values="Example.com", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "SUB.EXAMPLE.COM"}))

    def test_is_subdomain_ignores_trailing_dot_on_either_side(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_IS_SUBDOMAIN, values="example.com.", action=ACTION_APPROVE
        )
        self.assertTrue(rule.matches({"address": "sub.example.com."}))

    def test_missing_field_does_not_match(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        self.assertFalse(rule.matches({}))


class CleanTests(AutoApprovalRuleTestCase):
    def test_rejects_field_not_in_entitytype_schema(self):
        rule = AutoApprovalRule(
            project=self.project,
            entitytype=self.entitytype,
            name="rule",
            field="not-a-schema-property",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="x",
            action=ACTION_APPROVE,
        )
        with self.assertRaises(ValidationError):
            rule.clean()

    def test_accepts_field_defined_in_schema(self):
        rule = AutoApprovalRule(
            project=self.project,
            entitytype=self.entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="x",
            action=ACTION_APPROVE,
        )
        rule.clean()  # does not raise


class EvaluateAutoApprovalRulesTests(AutoApprovalRuleTestCase):
    """
    evaluate_auto_approval_rules() is a pure function: given (project, entitytype, data), it
    returns the resulting state or None - it never touches the database itself, so the caller
    (EntityManager.upsert_entity()) can fold the result directly into a single INSERT instead of
    inserting and then UPDATEing the state. The save/event side effects of that are covered
    end-to-end by test_entity_model.py's UpsertEntityAutoApprovalTests instead.
    """

    def test_matching_approve_rule_returns_enabled(self):
        self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )

        state = evaluate_all_auto_approval_rules_on_entity(self.project, self.entitytype, {"address": "1.1.1.1"})

        self.assertEqual(state, Entity.STATE_ENABLED)

    def test_matching_decline_rule_returns_disabled(self):
        self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_DECLINE
        )

        state = evaluate_all_auto_approval_rules_on_entity(self.project, self.entitytype, {"address": "1.1.1.1"})

        self.assertEqual(state, Entity.STATE_DISABLED)

    def test_decline_wins_over_approve(self):
        self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_DECLINE
        )

        state = evaluate_all_auto_approval_rules_on_entity(self.project, self.entitytype, {"address": "1.1.1.1"})

        self.assertEqual(state, Entity.STATE_DISABLED)

    def test_no_matching_rule_returns_none(self):
        self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="9.9.9.9", action=ACTION_APPROVE
        )

        state = evaluate_all_auto_approval_rules_on_entity(self.project, self.entitytype, {"address": "1.1.1.1"})

        self.assertIsNone(state)

    def test_rule_for_different_entitytype_is_ignored(self):
        self.make_rule(
            entitytype=self.other_entitytype,
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        state = evaluate_all_auto_approval_rules_on_entity(self.project, self.entitytype, {"address": "1.1.1.1"})

        self.assertIsNone(state)

    def test_rule_for_different_project_is_ignored(self):
        other_project = Project.objects.create(name="project-2")
        AutoApprovalRule.objects.create(
            project=other_project,
            entitytype=self.entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        state = evaluate_all_auto_approval_rules_on_entity(self.project, self.entitytype, {"address": "1.1.1.1"})

        self.assertIsNone(state)


class RunOnWaitingEntitiesTests(AutoApprovalRuleTestCase):
    """
    run_on_waiting_entities() applies one single rule to entities that already exist (the "Run
    now" button), so - unlike evaluate_auto_approval_rules() - no other rule of the
    project/entitytype is considered here.
    """

    def make_waiting_entity(self, address, entitytype=None, project=None):
        return Entity.objects.create(
            entitytype=entitytype or self.entitytype,
            project=project or self.project,
            data={"address": address},
            state=Entity.STATE_WAITING_APPROVAL,
        )

    def test_approve_rule_enables_matching_waiting_entities_and_adds_event(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        matching = self.make_waiting_entity("1.1.1.1")
        non_matching = self.make_waiting_entity("2.2.2.2")

        rule.run_on_waiting_entities()

        matching.refresh_from_db()
        non_matching.refresh_from_db()
        self.assertEqual(matching.state, Entity.STATE_ENABLED)
        self.assertEqual(non_matching.state, Entity.STATE_WAITING_APPROVAL)
        self.assertEqual(Event.objects.filter(entity=matching).count(), 1)

    def test_decline_rule_disables_matching_waiting_entities_without_event(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_DECLINE
        )
        matching = self.make_waiting_entity("1.1.1.1")

        rule.run_on_waiting_entities()

        matching.refresh_from_db()
        self.assertEqual(matching.state, Entity.STATE_DISABLED)
        self.assertEqual(Event.objects.filter(entity=matching).count(), 0)

    def test_only_entities_currently_waiting_for_approval_are_touched(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        already_enabled = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        already_declined = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "2.2.2.2"}, state=Entity.STATE_DISABLED
        )

        rule.run_on_waiting_entities()

        already_enabled.refresh_from_db()
        already_declined.refresh_from_db()
        self.assertEqual(already_enabled.state, Entity.STATE_ENABLED)
        self.assertEqual(already_declined.state, Entity.STATE_DISABLED)

    def test_only_entities_of_the_rules_own_entitytype_are_touched(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        other_type_entity = self.make_waiting_entity("1.1.1.1", entitytype=self.other_entitytype)

        rule.run_on_waiting_entities()

        other_type_entity.refresh_from_db()
        self.assertEqual(other_type_entity.state, Entity.STATE_WAITING_APPROVAL)

    def test_only_entities_of_the_rules_own_project_are_touched(self):
        rule = self.make_rule(
            field="address", operator=OPERATOR_STRING_EQUALS_SENSITIVE, values="1.1.1.1", action=ACTION_APPROVE
        )
        other_project = Project.objects.create(name="project-2")
        other_project_entity = self.make_waiting_entity("1.1.1.1", project=other_project)

        rule.run_on_waiting_entities()

        other_project_entity.refresh_from_db()
        self.assertEqual(other_project_entity.state, Entity.STATE_WAITING_APPROVAL)

    def test_other_rules_of_the_same_entitytype_are_not_considered(self):
        approve_rule = self.make_rule(
            name="approve-rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )
        # would win over the approve rule when a new entity is created, but running the approve
        # rule on its own must not apply it
        self.make_rule(
            name="decline-rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_DECLINE,
        )
        entity = self.make_waiting_entity("1.1.1.1")

        approve_rule.run_on_waiting_entities()

        entity.refresh_from_db()
        self.assertEqual(entity.state, Entity.STATE_ENABLED)
