from core.models import EntityType

from .base import ValidatedModelSerializer


class EntityTypeSerializer(ValidatedModelSerializer):
    class Meta:
        model = EntityType
        fields = ["name", "schema", "identifier_keys", "approval_required"]
