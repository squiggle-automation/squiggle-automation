from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from api.serializers import ConfigOptionSerializer

from ..forms import ConfigValueForm
from ..models import ConfigOption
from .mixins import ApiJsonPreviewMixin, ProjectOptionalMixin


class ConfigOptionListView(LoginRequiredMixin, ProjectOptionalMixin, ApiJsonPreviewMixin, ListView):
    model = ConfigOption
    context_object_name = "configoptions"
    template_name = "core/configoption_list.html"
    paginate_by = 100
    api_serializer_class = ConfigOptionSerializer


class ConfigOptionCreateView(LoginRequiredMixin, ProjectOptionalMixin, CreateView):
    model = ConfigOption
    fields = ["name", "description", "sensitive"]
    template_name = "core/configoption_form.html"
    success_url = reverse_lazy("core:configoptions")


class ConfigOptionUpdateView(LoginRequiredMixin, ProjectOptionalMixin, UpdateView):
    model = ConfigOption
    fields = ["name", "description", "sensitive"]
    template_name = "core/configoption_form.html"
    success_url = reverse_lazy("core:configoptions")

    def get_value_form(self):
        instance = self.object.get_default_value()

        return ConfigValueForm(
            data=self.request.POST or None,
            instance=instance,
            prefix="value",
            configoption=self.object,
            executor=None,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("value_form", self.get_value_form())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        value_form = self.get_value_form()

        if not (form.is_valid() and value_form.is_valid()):
            return self.render_to_response(self.get_context_data(form=form, value_form=value_form))

        with transaction.atomic():
            self.object = form.save()
            value_form.save()

        return redirect(self.get_success_url())


class ConfigOptionDeleteView(LoginRequiredMixin, ProjectOptionalMixin, DeleteView):
    model = ConfigOption
    template_name = "core/configoption_delete.html"
    success_url = reverse_lazy("core:configoptions")
