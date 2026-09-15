from rest_framework import serializers

from core.models import Container, EntityType, Executor, WorkerProfile

from .base import ValidatedModelSerializer


class ExecutorSerializer(ValidatedModelSerializer):
    container = serializers.SlugRelatedField(slug_field="name", queryset=Container.objects.all())
    input = serializers.SlugRelatedField(
        slug_field="name", queryset=EntityType.objects.all(), many=True, required=False
    )
    output = serializers.SlugRelatedField(
        slug_field="name", queryset=EntityType.objects.all(), many=True, required=False
    )
    workerprofile = serializers.SlugRelatedField(
        slug_field="name", queryset=WorkerProfile.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Executor
        fields = [
            "name",
            "container",
            "input",
            "output",
            "max_entities",
            "max_entities_timeout",
            "workerprofile",
            "keep_tmp_files",
            "enabled",
        ]
