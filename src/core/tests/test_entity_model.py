from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from ..models import AutoApprovalRule, Entity, EntityType, Event, Project
from ..models.autoapprovalrule import ACTION_APPROVE, OPERATOR_STRING_EQUALS_SENSITIVE

SCHEMA = {"type": "object", "properties": {"address": {"type": "string"}, "comment": {"type": "string"}}}


class EntityModelTestCase(TestCase):
    def setUp(self):
        # entitytype must exist before the project so that the upsert index gets created for it (see EntityType.save())
        self.entitytype = EntityType.objects.create(name="host", schema=SCHEMA, identifier_keys="address")
        self.approval_entitytype = EntityType.objects.create(
            name="host-approval", schema=SCHEMA, identifier_keys="address", approval_required=True
        )
        self.project = Project.objects.create(name="project-1")


class EntitySaveTests(EntityModelTestCase):
    def test_state_defaults_to_enabled_when_no_approval_required(self):
        entity = Entity.objects.create(entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"})
        self.assertEqual(entity.state, Entity.STATE_ENABLED)

    def test_state_defaults_to_waiting_approval_when_required(self):
        entity = Entity.objects.create(
            entitytype=self.approval_entitytype, project=self.project, data={"address": "1.1.1.1"}
        )
        self.assertEqual(entity.state, Entity.STATE_WAITING_APPROVAL)

    def test_creating_enabled_entity_adds_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_creating_waiting_approval_entity_adds_no_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1"},
            state=Entity.STATE_WAITING_APPROVAL,
        )
        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)

    def test_saving_unchanged_enabled_entity_does_not_add_another_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

        entity.data = {"address": "1.1.1.1", "comment": "updated"}
        entity.save()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_transition_from_waiting_approval_to_enabled_adds_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1"},
            state=Entity.STATE_WAITING_APPROVAL,
        )
        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)

        entity.state = Entity.STATE_ENABLED
        entity.save()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_transition_from_waiting_approval_to_disabled_adds_no_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype,
            project=self.project,
            data={"address": "1.1.1.1"},
            state=Entity.STATE_WAITING_APPROVAL,
        )

        entity.state = Entity.STATE_DISABLED
        entity.save()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)

    def test_changing_identifier_key_data_on_enabled_entity_adds_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

        entity.data = {"address": "9.9.9.9"}
        entity.save()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 2)

    def test_changing_identifier_key_data_on_disabled_entity_adds_no_event(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_DISABLED
        )

        entity.data = {"address": "9.9.9.9"}
        entity.save()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)


class EntityDeferredFieldTests(EntityModelTestCase):
    def test_init_does_not_dereference_deferred_state_and_data(self):
        # loading an entity with state/data deferred must not touch either field in __init__ -
        # doing so used to trigger a refresh_from_db() that builds a new instance with the
        # *other* field deferred, whose __init__ then re-triggered a refresh_from_db() of that
        # one, and so on forever (see wipe_platform_data, which cascade-deletes entities this way)
        Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )

        entity = Entity.objects.only("id", "entitytype_id", "project_id").get()

        self.assertIsNone(entity._old_state)
        self.assertIsNone(entity._old_data)
        self.assertIn("state", entity.get_deferred_fields())
        self.assertIn("data", entity.get_deferred_fields())


class EntityAddEventTests(EntityModelTestCase):
    def test_add_event_creates_event_when_enabled(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_ENABLED
        )
        Event.objects.filter(entity=entity).delete()

        entity.add_event()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_add_event_does_nothing_when_not_enabled(self):
        entity = Entity.objects.create(
            entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1"}, state=Entity.STATE_DISABLED
        )

        entity.add_event()

        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)


class EntityIdentifierValueTests(EntityModelTestCase):
    def test_identifier_value_uses_identifier_keys(self):
        entity = Entity(entitytype=self.entitytype, project=self.project, data={"address": "1.1.1.1", "comment": "x"})
        self.assertEqual(entity.identifier_value, "1.1.1.1")

    def test_identifier_value_falls_back_to_dash_when_missing(self):
        entity = Entity(entitytype=self.entitytype, project=self.project, data={})
        self.assertEqual(entity.identifier_value, "-")


class UpsertEntityTests(EntityModelTestCase):
    def test_insert_creates_new_entity(self):
        instance, created = Entity.objects.upsert_entity(self.entitytype, self.project, {"address": "1.1.1.1"})
        self.assertTrue(created)
        self.assertEqual(Entity.objects.filter(project=self.project, entitytype=self.entitytype).count(), 1)

        entity = Entity.objects.get(pk=instance.pk)
        self.assertEqual(entity.data, {"address": "1.1.1.1"})
        self.assertEqual(entity.state, Entity.STATE_ENABLED)

    def test_insert_uses_waiting_approval_state_if_required(self):
        instance, created = Entity.objects.upsert_entity(self.approval_entitytype, self.project, {"address": "1.1.1.1"})
        self.assertTrue(created)

        entity = Entity.objects.get(pk=instance.pk)
        self.assertEqual(entity.state, Entity.STATE_WAITING_APPROVAL)

    def test_insert_adds_event_by_default(self):
        instance, created = Entity.objects.upsert_entity(self.entitytype, self.project, {"address": "1.1.1.1"})
        self.assertTrue(created)
        self.assertEqual(Event.objects.filter(entity_id=instance.pk).count(), 1)

    def test_insert_can_skip_event(self):
        instance, created = Entity.objects.upsert_entity(
            self.entitytype, self.project, {"address": "1.1.1.1"}, add_event=False
        )
        self.assertTrue(created)
        self.assertEqual(Event.objects.filter(entity_id=instance.pk).count(), 0)

    def test_upsert_on_existing_identifier_updates_data_without_creating_duplicate(self):
        first, created_first = Entity.objects.upsert_entity(
            self.entitytype, self.project, {"address": "1.1.1.1", "comment": "initial"}
        )
        self.assertTrue(created_first)

        second, created_second = Entity.objects.upsert_entity(
            self.entitytype, self.project, {"address": "1.1.1.1", "comment": "updated"}
        )
        self.assertFalse(created_second)
        self.assertEqual(second.pk, first.pk)

        self.assertEqual(Entity.objects.filter(project=self.project, entitytype=self.entitytype).count(), 1)
        entity = Entity.objects.get(pk=first.pk)
        self.assertEqual(entity.data["comment"], "updated")
        self.assertEqual(entity.data["address"], "1.1.1.1")

    def test_upsert_on_existing_identifier_does_not_add_another_event(self):
        first, _ = Entity.objects.upsert_entity(self.entitytype, self.project, {"address": "1.1.1.1"})
        self.assertEqual(Event.objects.filter(entity_id=first.pk).count(), 1)

        Entity.objects.upsert_entity(self.entitytype, self.project, {"address": "1.1.1.1", "comment": "updated"})

        self.assertEqual(Event.objects.filter(entity_id=first.pk).count(), 1)

    def test_upsert_rejects_non_dict_data(self):
        with self.assertRaises(ValueError):
            Entity.objects.upsert_entity(self.entitytype, self.project, "not-a-dict")

    def test_get_entity_finds_by_identifier_keys(self):
        Entity.objects.upsert_entity(self.entitytype, self.project, {"address": "1.1.1.1", "comment": "x"})

        found = Entity.objects.get_entity(self.entitytype, self.project, {"address": "1.1.1.1"})
        self.assertEqual(found.data["address"], "1.1.1.1")

    def test_get_entity_raises_does_not_exist_for_unknown_identifier(self):
        with self.assertRaises(Entity.DoesNotExist):
            Entity.objects.get_entity(self.entitytype, self.project, {"address": "9.9.9.9"})

    def test_insert_with_single_quote_in_value_is_not_sql_injection(self):
        # data comes from executor output (attacker-influenced scan results), so a value
        # containing a single quote must be stored as-is rather than breaking out of the raw
        # SQL - see upsert_entity()
        instance, created = Entity.objects.upsert_entity(
            self.entitytype, self.project, {"address": "1.1.1.1", "comment": "test' OR '1'='1"}
        )
        self.assertTrue(created)

        entity = Entity.objects.get(pk=instance.pk)
        self.assertEqual(entity.data["comment"], "test' OR '1'='1")

    def test_update_with_single_quote_in_value_is_not_sql_injection(self):
        first, _ = Entity.objects.upsert_entity(self.entitytype, self.project, {"address": "1.1.1.1"})

        second, created = Entity.objects.upsert_entity(
            self.entitytype, self.project, {"address": "1.1.1.1", "comment": "it's updated"}
        )
        self.assertFalse(created)
        self.assertEqual(second.pk, first.pk)

        entity = Entity.objects.get(pk=first.pk)
        self.assertEqual(entity.data["comment"], "it's updated")

    def test_insert_with_single_quote_in_key_is_not_sql_injection(self):
        instance, created = Entity.objects.upsert_entity(
            self.entitytype, self.project, {"address": "1.1.1.1", "weird'key": "value"}
        )
        self.assertTrue(created)

        entity = Entity.objects.get(pk=instance.pk)
        self.assertEqual(entity.data["weird'key"], "value")


class UpsertEntityAutoApprovalTests(EntityModelTestCase):
    def test_insert_is_auto_approved_by_matching_rule(self):
        AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.approval_entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        instance, created = Entity.objects.upsert_entity(self.approval_entitytype, self.project, {"address": "1.1.1.1"})
        self.assertTrue(created)

        entity = Entity.objects.get(pk=instance.pk)
        self.assertEqual(entity.state, Entity.STATE_ENABLED)
        self.assertEqual(Event.objects.filter(entity=entity).count(), 1)

    def test_insert_auto_approved_by_matching_rule_writes_the_entity_only_once(self):
        # the auto-approval rules must be evaluated before the INSERT, so the entity is written
        # with its final state directly - never inserted as waiting and then UPDATEd
        AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.approval_entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        with CaptureQueriesContext(connection) as queries:
            Entity.objects.upsert_entity(self.approval_entitytype, self.project, {"address": "1.1.1.1"})

        entity_table = Entity._meta.db_table
        writes_to_entity_table = [
            q["sql"]
            for q in queries.captured_queries
            if entity_table in q["sql"] and q["sql"].split(maxsplit=1)[0].upper() in ("INSERT", "UPDATE")
        ]
        self.assertEqual(len(writes_to_entity_table), 1, writes_to_entity_table)

    def test_insert_without_matching_rule_stays_waiting_approval(self):
        AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.approval_entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="9.9.9.9",
            action=ACTION_APPROVE,
        )

        instance, created = Entity.objects.upsert_entity(self.approval_entitytype, self.project, {"address": "1.1.1.1"})
        self.assertTrue(created)

        entity = Entity.objects.get(pk=instance.pk)
        self.assertEqual(entity.state, Entity.STATE_WAITING_APPROVAL)
        self.assertEqual(Event.objects.filter(entity=entity).count(), 0)

    def test_update_of_existing_waiting_entity_does_not_change_its_state(self):
        first, _ = Entity.objects.upsert_entity(self.approval_entitytype, self.project, {"address": "1.1.1.1"})
        self.assertEqual(first.state, Entity.STATE_WAITING_APPROVAL)

        # rule added only after the entity already exists - the raw upsert SQL's ON CONFLICT
        # branch never touches the state column, so even though this new rule would now match,
        # it must not retroactively change an already-existing entity's state
        AutoApprovalRule.objects.create(
            project=self.project,
            entitytype=self.approval_entitytype,
            name="rule",
            field="address",
            operator=OPERATOR_STRING_EQUALS_SENSITIVE,
            values="1.1.1.1",
            action=ACTION_APPROVE,
        )

        second, created = Entity.objects.upsert_entity(
            self.approval_entitytype, self.project, {"address": "1.1.1.1", "comment": "updated"}
        )
        self.assertFalse(created)

        entity = Entity.objects.get(pk=first.pk)
        self.assertEqual(entity.state, Entity.STATE_WAITING_APPROVAL)
