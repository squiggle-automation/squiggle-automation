import jsonschema
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.utils.translation import gettext_lazy as _


# NOTE: this model is edited via both a web form (fields=[...] on EntityTypeCreateView/
# EntityTypeUpdateView in core/views/entitytype.py) and an API serializer
# (api/serializers/entitytype.py). If you add, remove, or rename a field, update both.
class EntityType(models.Model):
    class Meta:
        ordering = ["name"]

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        verbose_name=_("Name"),
    )

    schema = models.JSONField(
        blank=False,
        null=False,
        verbose_name=_("JSON schema"),
    )

    identifier_keys = models.CharField(
        blank=False,
        null=False,
        verbose_name=_("Keys that together uniquely identify this entity"),
        help_text=_("Multiple keys can be separated with comma. Only top level keys in the JSON data are possible."),
    )

    approval_required = models.BooleanField(
        default=False,
        null=False,
        verbose_name=_("Approval of new entities is required"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # store old names to check if index needs to be changed
        self._old_identified_keys = self.identifier_keys

    def __str__(self):
        return self.name

    def clean(self):
        # validate json schema
        try:
            jsonschema.Draft202012Validator.check_schema(self.schema)
        except jsonschema.SchemaError:
            raise ValidationError({"schema": _("Schema is invalid.")})

        # check that identifiers are defined in schema
        defined_keys = self.schema.get("properties", {}).keys()
        for i in self.identifier_keys_list:
            if i not in defined_keys:
                raise ValidationError({"identifier_keys": _("Specified identifier keys are not defined in schema.")})

    def save(self, *args, **kwargs):
        adding = self._state.adding

        super().save(*args, **kwargs)

        # if newly added or identifier changed, create / update indexes of this entitytype
        if adding or self.identifier_keys != self._old_identified_keys:
            from .entity import create_index

            create_index(
                entitytype_list=[
                    self,
                ]
            )

        self._old_identified_keys = self.identifier_keys

    def delete(self, *args, **kwargs):
        old_id = self.id
        super().delete(*args, **kwargs)

        # delete indexes for this entitytype
        from .entity import delete_index

        delete_index(entitytype_deleted=old_id)

    @property
    def identifier_keys_list(self):
        return list(map(lambda x: x.strip(), self.identifier_keys.split(",")))

    @property
    def schema_keys_list(self):
        """
        The top level keys of the schema, i.e. the possible columns of an entity list.

        Ordered by how useful they are: the identifier keys first (they are what an entity is
        recognised by), then the other required ones, then the rest in schema order.
        """
        properties = self.schema.get("properties") if isinstance(self.schema, dict) else None
        if not isinstance(properties, dict):
            return []

        keys = [i for i in self.identifier_keys_list if i in properties]
        keys += [i for i in self.schema.get("required", []) if i in properties and i not in keys]
        keys += [i for i in properties if i not in keys]

        return keys

    def schema_key_type(self, key):
        """
        The json schema type of one top level key ("string", "number", ...), or None if the key
        is not in the schema or has no single type.
        """
        properties = self.schema.get("properties") if isinstance(self.schema, dict) else None
        if not isinstance(properties, dict):
            return None

        definition = properties.get(key)
        if not isinstance(definition, dict):
            return None

        key_type = definition.get("type")

        return key_type if isinstance(key_type, str) else None
