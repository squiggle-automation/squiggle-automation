from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from api.serializers import EntityTypeSerializer

from ..models import EntityType
from .mixins import ApiJsonPreviewMixin, ProjectOptionalMixin


class EntityTypeListView(LoginRequiredMixin, ProjectOptionalMixin, ApiJsonPreviewMixin, ListView):
    model = EntityType
    context_object_name = "entitytypes"
    template_name = "core/entitytype_list.html"
    paginate_by = 100
    api_serializer_class = EntityTypeSerializer


class EntityTypeCreateView(LoginRequiredMixin, ProjectOptionalMixin, CreateView):
    model = EntityType
    fields = ["name", "schema", "identifier_keys", "approval_required"]
    template_name = "core/entitytype_form.html"
    success_url = reverse_lazy("core:entitytypes")


class EntityTypeUpdateView(LoginRequiredMixin, ProjectOptionalMixin, UpdateView):
    model = EntityType
    fields = ["name", "schema", "identifier_keys", "approval_required"]
    template_name = "core/entitytype_form.html"
    success_url = reverse_lazy("core:entitytypes")


class EntityTypeDeleteView(LoginRequiredMixin, ProjectOptionalMixin, DeleteView):
    model = EntityType
    template_name = "core/entitytype_delete.html"
    success_url = reverse_lazy("core:entitytypes")
