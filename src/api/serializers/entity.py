from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models import Entity

# state names as used in the API (and in the ?state= filter of the entity list)
STATE_NAMES = {
    Entity.STATE_ENABLED: "enabled",
    Entity.STATE_WAITING_APPROVAL: "waiting_approval",
    Entity.STATE_DISABLED: "disabled",
}


class EntitySerializer(serializers.Serializer):
    """
    The entity type must be passed as context["entitytype"] to validate data against its schema.

    state is read-only, so the approval flow can't be bypassed.
    """

    data = serializers.JSONField()
    state = serializers.SerializerMethodField()

    def get_state(self, obj):
        return STATE_NAMES[obj.state]

    def validate_data(self, value):
        entitytype = self.context["entitytype"]

        if not isinstance(value, dict):
            raise serializers.ValidationError("Data must be an object.")

        missing = [key for key in entitytype.identifier_keys_list if key not in value]
        if missing:
            raise serializers.ValidationError(f"Missing identifier keys: {', '.join(missing)}")

        # same validation as the model's clean() (data against the schema of the entity type)
        # without needing an unsaved instance, which would also be created for existing entities
        entity = Entity(entitytype=entitytype, data=value)
        try:
            entity.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict.get("data", e.messages))

        return value
