from core.models import Project

from .base import ValidatedModelSerializer


class ProjectSerializer(ValidatedModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "run_executors", "created_at"]
        read_only_fields = ["created_at"]
