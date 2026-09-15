from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView
from django.views.generic.base import TemplateResponseMixin, View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from api.serializers import ExecutorSerializer

from ..forms import ConfigValueForm
from ..models import Executor
from ..tasks import run_executor_all_entities
from .mixins import ApiJsonPreviewMixin, ProjectOptionalMixin


class ExecutorListView(LoginRequiredMixin, ProjectOptionalMixin, ApiJsonPreviewMixin, ListView):
    model = Executor
    context_object_name = "executors"
    template_name = "core/executor_list.html"
    paginate_by = 100
    api_serializer_class = ExecutorSerializer


class ExecutorCreateView(LoginRequiredMixin, ProjectOptionalMixin, CreateView):
    model = Executor
    fields = [
        "name",
        "container",
        "input",
        "output",
        "max_entities",
        "max_entities_timeout",
        "workerprofile",
        "enabled",
        "keep_tmp_files",
    ]
    template_name = "core/executor_form.html"
    success_url = reverse_lazy("core:executors")


class ExecutorUpdateView(LoginRequiredMixin, ProjectOptionalMixin, UpdateView):
    model = Executor
    fields = [
        "name",
        "container",
        "input",
        "output",
        "max_entities",
        "max_entities_timeout",
        "workerprofile",
        "enabled",
        "keep_tmp_files",
    ]
    template_name = "core/executor_form.html"
    success_url = reverse_lazy("core:executors")


class ExecutorConfigView(LoginRequiredMixin, ProjectOptionalMixin, SingleObjectMixin, TemplateResponseMixin, View):
    model = Executor
    template_name = "core/executor_config.html"

    def get_success_url(self):
        return reverse_lazy("core:executors")

    def get_value_forms(self):
        forms = []
        for configoption in self.object.container.configoptions.all():
            configvalue = configoption.get_value(self.object, no_default=True)
            forms.append(
                ConfigValueForm(
                    data=self.request.POST or None,
                    instance=configvalue,
                    configoption=configoption,
                    executor=self.object,
                    prefix=f"value-{configoption.pk}",
                )
            )
        return forms

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("value_forms", self.get_value_forms())
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        value_forms = self.get_value_forms()

        if not all(f.is_valid() for f in value_forms):
            return self.render_to_response(self.get_context_data(value_forms=value_forms))

        with transaction.atomic():
            for value_form in value_forms:
                value_form.save()

        return redirect(self.get_success_url())


class ExecutorDeleteView(LoginRequiredMixin, ProjectOptionalMixin, DeleteView):
    model = Executor
    template_name = "core/executor_delete.html"
    success_url = reverse_lazy("core:executors")


class ExecutorRunAllEntitiesView(LoginRequiredMixin, ProjectOptionalMixin, View):
    def post(self, request, *args, **kwargs):
        executor = get_object_or_404(Executor, pk=kwargs["pk"])

        if not self.active_project:
            messages.error(request, _("No projet opened."))
        elif not executor.enabled:
            messages.error(request, _("Executor is disabled."))
        else:
            run_executor_all_entities.delay(executor.pk, self.active_project.pk)
            messages.success(
                request, _('Running "%(name)s" on all entities in this project.') % {"name": executor.name}
            )

        return redirect("core:executors")
