import ipaddress
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .entitytype import EntityType
from .project import Project

ACTION_APPROVE = "approve"
ACTION_DECLINE = "decline"

ACTION_CHOICES = {
    ACTION_APPROVE: _("Approve"),
    ACTION_DECLINE: _("Decline"),
}

OPERATOR_STRING_EQUALS_SENSITIVE = "string_equals_sensitive"
OPERATOR_STRING_EQUALS_INSENSITIVE = "string_equals_insensitive"
OPERATOR_REGEX = "regex"
OPERATOR_IP_IN_RANGE = "ip_in_range"
OPERATOR_IS_SUBDOMAIN = "is_subdomain"

OPERATOR_CHOICES = {
    OPERATOR_STRING_EQUALS_SENSITIVE: _("Equals (case-sensitive)"),
    OPERATOR_STRING_EQUALS_INSENSITIVE: _("Equals (case-insensitive)"),
    OPERATOR_REGEX: _("Matches regex"),
    OPERATOR_IP_IN_RANGE: _("Is in IP range"),
    OPERATOR_IS_SUBDOMAIN: _("Is subdomain of"),
}


def _compare_string_equals_sensitive(entity_value, rule_value):
    return str(entity_value) == rule_value


def _compare_string_equals_insensitive(entity_value, rule_value):
    return str(entity_value).casefold() == rule_value.casefold()


def _compare_regex(entity_value, rule_value):
    try:
        return bool(re.search(rule_value, str(entity_value)))
    except re.error:
        return False


def _compare_ip_in_range(entity_value, rule_value):
    try:
        ip = ipaddress.ip_address(str(entity_value))
        network = ipaddress.ip_network(rule_value, strict=False)
    except ValueError:
        return False
    return ip in network


def _compare_is_subdomain(entity_value, rule_value):
    # case-insensitive (like DNS names), and a trailing "." (FQDN notation) is ignored on both
    # sides - the domain itself does not count as its own subdomain
    entity_value = str(entity_value).casefold().rstrip(".")
    rule_value = rule_value.casefold().rstrip(".")
    if not rule_value or entity_value == rule_value:
        return False
    return entity_value.endswith("." + rule_value)


# extensible: add a new operator by adding a key to OPERATOR_CHOICES and a matching entry here.
# Every function takes (entity_value, rule_value) and must never raise - an invalid/unparsable
# value just means "no match", it must not break entity creation.
OPERATOR_FUNCTIONS = {
    OPERATOR_STRING_EQUALS_SENSITIVE: _compare_string_equals_sensitive,
    OPERATOR_STRING_EQUALS_INSENSITIVE: _compare_string_equals_insensitive,
    OPERATOR_REGEX: _compare_regex,
    OPERATOR_IP_IN_RANGE: _compare_ip_in_range,
    OPERATOR_IS_SUBDOMAIN: _compare_is_subdomain,
}


# NOTE: this model is edited via both a web form (fields=[...] on AutoApprovalRuleCreateView/
# AutoApprovalRuleUpdateView in core/views/autoapprovalrule.py) and an API serializer
# (api/serializers/autoapprovalrule.py). If you add, remove, or rename a field, update both.
class AutoApprovalRule(models.Model):
    class Meta:
        ordering = ["project", "entitytype", "name"]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        verbose_name=_("Project"),
    )

    entitytype = models.ForeignKey(
        EntityType,
        on_delete=models.CASCADE,
        verbose_name=_("Entity type"),
    )

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        verbose_name=_("Name"),
    )

    field = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        verbose_name=_("Field"),
        help_text=_("Key in the entity's data to check. Must be a property of the entity type's schema."),
    )

    operator = models.CharField(
        max_length=255,
        choices=OPERATOR_CHOICES,
        blank=False,
        null=False,
        verbose_name=_("Operator"),
    )

    values = models.TextField(
        blank=False,
        null=False,
        verbose_name=_("Values"),
        help_text=_("One value per line. The rule matches if any of these values match (OR)."),
    )

    action = models.CharField(
        max_length=255,
        choices=ACTION_CHOICES,
        blank=False,
        null=False,
        verbose_name=_("Action"),
    )

    def __str__(self):
        return f"{self.name} ({self.entitytype})"

    def clean(self):
        # field must be a property of the entitytype's schema - same check EntityType.clean()
        # does for identifier_keys
        if self.entitytype_id:
            defined_keys = self.entitytype.schema.get("properties", {}).keys()
            if self.field not in defined_keys:
                raise ValidationError({"field": _("Field is not defined in the schema of the entity type.")})

    @property
    def values_list(self):
        return [line.strip() for line in self.values.splitlines() if line.strip()]

    def matches(self, data):
        """Whether this rule matches the given entity data dict (any of its values matching wins)."""
        entity_value = data.get(self.field)
        if entity_value is None:
            return False

        compare = OPERATOR_FUNCTIONS[self.operator]
        return any(compare(entity_value, rule_value) for rule_value in self.values_list)

    def run_on_waiting_entities(self):
        """
        Applies this rule to every entity of its project/entitytype that is currently waiting
        for approval, and saves the ones it matches. Used by the "Run now" button (via the
        run_auto_approval_rule task) to apply a rule to entities that already exist - new
        entities are handled by evaluate_auto_approval_rules() while they are created.
        """
        # local import to avoid a circular import
        from .entity import Entity

        entities = Entity.objects.filter(
            project=self.project, entitytype=self.entitytype, state=Entity.STATE_WAITING_APPROVAL
        )
        for entity in entities:
            state = _evaluate_rules([self], entity.data)
            if state is not None:
                entity.state = state
                entity.save()  # also adds the event if the new state is STATE_ENABLED


def evaluate_all_auto_approval_rules_on_entity(project, entitytype, data):
    """
    Evaluates all auto-approval rules for (project, entitytype) against data, and returns the
    resulting Entity state, or None if no rule matches. Takes plain values rather than an Entity
    instance so the caller can fold the result into an INSERT instead of having to UPDATE the
    state afterwards.
    """
    rules = AutoApprovalRule.objects.filter(project=project, entitytype=entitytype)
    return _evaluate_rules(rules, data)


def _evaluate_rules(rules, data):
    """
    Evaluates the given auto-approval rules against data, and returns the resulting Entity state
    (a matching "decline" rule always wins over a matching "approve" rule), or None if no rule
    matches.
    """
    # local import to avoid a circular import, see EntityType.save()
    from .entity import Entity

    matching_actions = {rule.action for rule in rules if rule.matches(data)}

    if ACTION_DECLINE in matching_actions:
        return Entity.STATE_DISABLED
    if ACTION_APPROVE in matching_actions:
        return Entity.STATE_ENABLED
    return None
