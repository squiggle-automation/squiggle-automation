from rest_framework import serializers

from core.models import ConfigOption, Container

from .base import ValidatedModelSerializer


class ContainerSerializer(ValidatedModelSerializer):
    configoptions = serializers.SlugRelatedField(
        slug_field="name", queryset=ConfigOption.objects.all(), many=True, required=False
    )

    class Meta:
        model = Container
        fields = ["name", "image", "image_tag", "cap_net_raw", "net_host", "configoptions"]
