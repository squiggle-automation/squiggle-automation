from rest_framework import serializers

from core.models import AutoApprovalRule, EntityType

from .base import ValidatedModelSerializer


class AutoApprovalRuleSerializer(ValidatedModelSerializer):
    # project is not a field here - it comes from the URL (see ProjectScopedViewSetMixin in
    # api/views.py), the same as the web UI's AutoApprovalRuleCreateView/UpdateView never has
    # project in their form fields either
    entitytype = serializers.SlugRelatedField(slug_field="name", queryset=EntityType.objects.all())

    class Meta:
        model = AutoApprovalRule
        fields = ["entitytype", "name", "field", "operator", "values", "action"]

    def get_validation_instance(self):
        # on create, the project (from the URL) is needed for the unique name check in clean()
        instance = super().get_validation_instance()
        if instance.project_id is None:
            instance.project = self.context["view"].get_project()
        return instance
