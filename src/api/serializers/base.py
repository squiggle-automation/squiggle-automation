from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class ValidatedModelSerializer(serializers.ModelSerializer):
    """
    ModelSerializer that also runs the model's own clean() during validation.

    A plain ModelSerializer does not do this (unlike Django's ModelForm), so without this,
    model-level validation (e.g. EntityType.clean()) would only apply to the web UI, not the API.
    """

    def get_validation_instance(self):
        """The instance clean() runs on - override to set fields that are not part of the serializer."""
        return self.instance or self.Meta.model()

    def validate(self, attrs):
        model = self.Meta.model
        # many-to-many fields can't be set on an unsaved/not-yet-committed instance (Django
        # requires .set() on a saved instance) and aren't part of clean() anyway - skip them
        m2m_field_names = {f.name for f in model._meta.many_to_many}

        instance = self.get_validation_instance()
        for key, value in attrs.items():
            if key in m2m_field_names:
                continue
            setattr(instance, key, value)

        try:
            instance.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)

        return attrs
