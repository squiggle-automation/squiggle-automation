from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from api.serializers import WorkerProfileSerializer

from ..models import WorkerProfile
from .mixins import ApiJsonPreviewMixin, ProjectOptionalMixin


class WorkerProfileListView(LoginRequiredMixin, ProjectOptionalMixin, ApiJsonPreviewMixin, ListView):
    model = WorkerProfile
    context_object_name = "workers"
    template_name = "core/workerprofile_list.html"
    paginate_by = 100
    api_serializer_class = WorkerProfileSerializer


class WorkerProfileCreateView(LoginRequiredMixin, ProjectOptionalMixin, CreateView):
    model = WorkerProfile
    fields = ["name", "concurrency", "is_default"]
    template_name = "core/workerprofile_form.html"
    success_url = reverse_lazy("core:workerprofiles")


class WorkerProfileUpdateView(LoginRequiredMixin, ProjectOptionalMixin, UpdateView):
    model = WorkerProfile
    fields = ["concurrency", "is_default"]
    template_name = "core/workerprofile_form.html"
    success_url = reverse_lazy("core:workerprofiles")


class WorkerProfileDeleteView(LoginRequiredMixin, ProjectOptionalMixin, DeleteView):
    model = WorkerProfile
    template_name = "core/workerprofile_delete.html"
    success_url = reverse_lazy("core:workerprofiles")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ValidationError as e:
            messages.error(self.request, e.message)
            return redirect(self.success_url)
