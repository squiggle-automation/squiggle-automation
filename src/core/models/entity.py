import json

import jsonschema
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import Q
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.utils.translation import gettext_lazy as _

from .autoapprovalrule import evaluate_all_auto_approval_rules_on_entity
from .entitytype import EntityType
from .event import Event
from .project import Project


class EntityQuerySet(models.QuerySet):
    def order_entity_by_values(self, entitytype, keys=None, descending=False):
        """
        Order by the values of the given data keys, or by the identifier keys if none are given.

        How a key is ordered depends on its type in the schema of the entity type: a number key
        is ordered on the jsonb value (data->'key'), so that 80 sorts before 443 instead of
        after it, every other key on its text (data->>'key').

        Ordering on the text is not just about strings sorting like strings: the unique index of
        the identifier keys is built on data->>'key' (see create_index()), so ordering by them
        is an index scan rather than a sort of the whole (entitytype, project) slice - which is
        what the entity list does by default.
        """
        if keys is None:
            keys = entitytype.identifier_keys_list

        order_by = []
        for key in keys:
            if entitytype.schema_key_type(key) in ("integer", "number"):
                expression = KeyTransform(key, "data")
            else:
                expression = KeyTextTransform(key, "data")

            # plain asc()/desc() on purpose: they are what a btree index can be scanned
            # forwards/backwards for, so no nulls_last here - entities without the key sort
            # last when ascending and first when descending
            order_by.append(expression.desc() if descending else expression.asc())

        # a data key does not have to be unique (only the identifier keys together are), so the
        # order needs a tiebreaker - without it, rows can repeat or be skipped between pages
        order_by.append("-pk" if descending else "pk")

        return self.order_by(*order_by)

    def filter_entity_by_values(self, filters):
        """
        Filter on a substring of the values of data keys, given as a dict of key -> substring.

        Matching is case-insensitive and works for every schema type, because data->>'key'
        renders a number or boolean as text too ("80" matches both 80 and 8080).
        """
        queryset = self
        for key, value in filters.items():
            queryset = queryset.filter(**{f"data__{key}__icontains": value})

        return queryset

    def search_entity_values(self, keys, term):
        """Filter on a substring that has to appear in the value of any one of the given keys."""
        query = Q()
        for key in keys:
            query |= Q(**{f"data__{key}__icontains": term})

        return self.filter(query)


class EntityManager(models.Manager):
    def get_queryset(self):
        return EntityQuerySet(self.model, using=self._db)

    def get_entity(self, entitytype, project, data):
        # build query based on the identifier keys
        query = {}
        try:
            for key in entitytype.identifier_keys_list:
                query[f"data__{key}"] = data[key]
        except KeyError:
            raise ValueError("data does not contain all identifier keys")

        return self.get(entitytype=entitytype, project=project, **query)

    def upsert_entity(self, entitytype, project, data, add_event=True):
        # Example query for UPSERT:
        #
        # INSERT INTO core_entity (entitytype_id, data, state)
        # VALUES (1, '{"address": "1.2.3.4"}'::jsonb, 1)
        # ON CONFLICT (entitytype_id, (data->>'address'))
        # WHERE entitytype_id = 1
        # DO UPDATE SET data = core_entity.data || jsonb_build_object(
        #     'comment', 'test2'
        # );
        #
        # This only works if a UNIQUE index is there for the values in the "ON CONFLICT" part.
        # The unique index is created and updated by the EntityType model
        #
        # The state is only included in the INSERT part, but not in the DO UPDATE part.
        # So it is only set for new rows, but not changed for existing rows.

        if type(data) != dict:
            raise ValueError("data must be a dict")

        all_keys = data.keys()
        identifier_keys = entitytype.identifier_keys_list
        table_name = self.model._meta.db_table

        # all data as json (for insert - will be passed as bind parameter)
        all_data_json = json.dumps(data)

        # data that should be updated
        # both keys and values are passed as bind parameters, the final format is
        # key_1, value_1, key_2, value_2, ... to match jsonb_build_object()
        #
        # format example (for 2 values)
        # update_data_list: ['%s, %s, %s, %s']
        # update_data_parameters: ['key_1', 'value_1', 'key_2', 'value_2']
        update_data_list = ", ".join(["%s, %s"] * len(all_keys))
        update_data_parameters = [item for key in all_keys for item in (key, data[key])]

        # list of attributes that define the conflict/unique constraint
        # format example: (data->>'address'), (data->>'subnet')
        conflict_list = ", ".join([f"(data->>'{i}')" for i in identifier_keys])

        # new state depends on settings in entitytype - if approval is required, a matching
        # auto-approval rule (see AutoApprovalRule) may already decide it here, so that the
        # entity is inserted with its final state right away instead of needing a second UPDATE
        new_state = Entity.STATE_ENABLED
        if entitytype.approval_required:
            new_state = (
                evaluate_all_auto_approval_rules_on_entity(project, entitytype, data) or Entity.STATE_WAITING_APPROVAL
            )

        results = self.raw(
            f"""INSERT INTO {table_name} (entitytype_id, project_id, data, state)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (entitytype_id, project_id, {conflict_list})
                WHERE entitytype_id = %s AND project_id = %s
                DO UPDATE SET
                    data = {table_name}.data || jsonb_build_object(
                        {update_data_list}
                )
                RETURNING id, entitytype_id, project_id, data, state, (xmax = 0) AS created;""",
            [
                entitytype.id,
                project.id,
                all_data_json,
                new_state,
                entitytype.id,
                project.id,
                *update_data_parameters,
            ],
        )

        if results:
            instance = results[0]

            # add_event() itself only creates an Event if the entity ended up STATE_ENABLED -
            # either because no approval was required, or because an auto-approval rule (see
            # above) already approved it
            if instance.created and add_event:
                instance.add_event()

            return instance, instance.created
        else:
            return None, False


class Entity(models.Model):
    class Meta:
        ordering = ["project", "entitytype"]

    STATE_ENABLED = 1
    STATE_WAITING_APPROVAL = 2
    STATE_DISABLED = 3

    STATE_CHOICES = {
        STATE_ENABLED: _("Enabled"),
        STATE_WAITING_APPROVAL: _("Waiting for approval"),
        STATE_DISABLED: _("Disabled"),
    }

    objects = EntityManager()

    entitytype = models.ForeignKey(
        EntityType,
        on_delete=models.CASCADE,
        verbose_name=_("Type"),
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        verbose_name=_("Project"),
    )

    data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("Data"),
    )

    state = models.IntegerField(
        choices=STATE_CHOICES,
        verbose_name=_("State"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._old_state = self.state
        self._old_data = self.data

    def __str__(self):
        return f"{self.entitytype}: {self.identifier_value}"

    def clean(self):
        # validate entity data against schema of entitytype
        try:
            jsonschema.validate(
                instance=self.data,
                schema=self.entitytype.schema,
                format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
            )
        except jsonschema.ValidationError:
            raise ValidationError({"data": _("Data does not match the schema of this entity type.")})
        except jsonschema.SchemaError:
            raise ValidationError({"data": _("Schema of this entity type is invalid.")})

    def save(self, *args, **kwargs):
        adding = self._state.adding

        if not self.state:
            if self.entitytype.approval_required:
                self.state = self.STATE_WAITING_APPROVAL
            else:
                self.state = self.STATE_ENABLED

        super().save(*args, **kwargs)

        # there are some cases in which we want to create a new event for this entity
        # - it was newly added
        # - state was changed to enabled (and was not enabled before)
        # - the identifier key data changed, which means it can be seen as new entity
        state_changed_to_enabled = self._old_state != self.state and self.state == self.STATE_ENABLED
        identifier_data_changed = not adding and any(
            (self._old_data or {}).get(key) != (self.data or {}).get(key)
            for key in self.entitytype.identifier_keys_list
        )
        if adding or state_changed_to_enabled or identifier_data_changed:
            self.add_event()

    @property
    def identifier_value(self):
        data = []
        for key in self.entitytype.identifier_keys_list:
            try:
                data.append(str(self.data[key]))
            except (KeyError, TypeError):
                data.append("-")

        return ",".join(data)

    def add_event(self):
        if self.state == self.STATE_ENABLED:
            Event.objects.create(entity=self, project=self.project)


def create_index(entitytype_list=None, project_list=None):
    """
    Create the required indexes in the database.

    If entitytype_list is set, the indexes for this entitytype are updated for all projects.
    If project_list is set, the indexes for all entitytpes are updated for this project.

    If both are not set, all indexes are updated (should not be required.)
    """
    if entitytype_list is None:
        entitytype_list = EntityType.objects.all()
    if project_list is None:
        project_list = Project.objects.all()

    entity_table = Entity._meta.db_table

    for project in project_list:
        for entitytype in entitytype_list:
            index_name = f"{entity_table}_type_{entitytype.id}_project_{project.id}"

            constraint_list = ", ".join([f"(data->>'{i}')" for i in entitytype.identifier_keys_list])

            with connection.cursor() as cursor:
                cursor.execute(f"""DROP INDEX IF EXISTS {index_name};""")
                cursor.execute(
                    f"""CREATE UNIQUE INDEX {index_name}
                                ON {entity_table} (entitytype_id, project_id, {constraint_list}) WHERE entitytype_id = %s AND project_id = %s;""",
                    [entitytype.id, project.id],
                )


def delete_index(entitytype_deleted=None, project_deleted=None):
    """
    Delete all indexes for an entitytype or project.
    The parameters are the old IDs and not objects.
    Exactly one needs to be set
    """
    if (entitytype_deleted is not None and project_deleted is not None) or (
        entitytype_deleted is None and project_deleted is None
    ):
        raise ValueError("entitytype or project need to be set, but not both")

    if entitytype_deleted is not None:
        entitytype_list = [
            entitytype_deleted,
        ]
        project_list = Project.objects.all().values_list("pk", flat=True)
    elif project_deleted is not None:
        entitytype_list = EntityType.objects.all().values_list("pk", flat=True)
        project_list = [
            project_deleted,
        ]

    entity_table = Entity._meta.db_table

    for project_id in project_list:
        for entitytype_id in entitytype_list:
            index_name = f"{entity_table}_type_{entitytype_id}_project_{project_id}"
            with connection.cursor() as cursor:
                cursor.execute(f"""DROP INDEX IF EXISTS {index_name};""")
