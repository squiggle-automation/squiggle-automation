from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from api.serializers import ContainerSerializer

from ..models import Container
from .mixins import ApiJsonPreviewMixin, ProjectOptionalMixin


class ContainerListView(LoginRequiredMixin, ProjectOptionalMixin, ApiJsonPreviewMixin, ListView):
    model = Container
    context_object_name = "containers"
    template_name = "core/container_list.html"
    paginate_by = 100
    api_serializer_class = ContainerSerializer


class ContainerCreateView(LoginRequiredMixin, ProjectOptionalMixin, CreateView):
    model = Container
    fields = ["name", "image", "image_tag", "cap_net_raw", "net_host", "configoptions"]
    template_name = "core/container_form.html"
    success_url = reverse_lazy("core:containers")


class ContainerUpdateView(LoginRequiredMixin, ProjectOptionalMixin, UpdateView):
    model = Container
    fields = ["name", "image", "image_tag", "cap_net_raw", "net_host", "configoptions"]
    template_name = "core/container_form.html"
    success_url = reverse_lazy("core:containers")


class ContainerDeleteView(LoginRequiredMixin, ProjectOptionalMixin, DeleteView):
    model = Container
    template_name = "core/container_delete.html"
    success_url = reverse_lazy("core:containers")
