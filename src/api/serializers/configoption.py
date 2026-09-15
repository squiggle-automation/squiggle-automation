from core.models import ConfigOption

from .base import ValidatedModelSerializer


class ConfigOptionSerializer(ValidatedModelSerializer):
    class Meta:
        model = ConfigOption
        fields = ["name", "description", "sensitive"]
