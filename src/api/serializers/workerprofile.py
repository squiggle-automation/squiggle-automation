from core.models import WorkerProfile

from .base import ValidatedModelSerializer


class WorkerProfileSerializer(ValidatedModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = ["name", "concurrency", "is_default"]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            # name is the celery queue name - workers are already bound to it, so (like the
            # web UI's WorkerProfileUpdateView) it can only be set on creation, not renamed
            fields["name"].read_only = True
        return fields
