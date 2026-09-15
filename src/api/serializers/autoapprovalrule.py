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
        fields = ["id", "entitytype", "name", "field", "operator", "values", "action"]
