from rest_framework import serializers


class ConfigValueSerializer(serializers.Serializer):
    """A single config value. On write, a null/blank value clears it."""

    value = serializers.CharField(allow_blank=True, allow_null=True, max_length=10000)
