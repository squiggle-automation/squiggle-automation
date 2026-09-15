from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, View
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from api.serializers import AutoApprovalRuleSerializer

from ..models import AutoApprovalRule
from ..tasks import run_auto_approval_rule
from .mixins import ApiJsonPreviewMixin, ProjectRequiredMixin


class AutoApprovalRuleListView(LoginRequiredMixin, ProjectRequiredMixin, ApiJsonPreviewMixin, ListView):
    model = AutoApprovalRule
    context_object_name = "autoapprovalrules"
    template_name = "core/autoapprovalrule_list.html"
    paginate_by = 100
    api_serializer_class = AutoApprovalRuleSerializer

    def get_queryset(self):
        return super().get_queryset().filter(project=self.project)


class AutoApprovalRuleCreateView(LoginRequiredMixin, ProjectRequiredMixin, CreateView):
    model = AutoApprovalRule
    fields = ["entitytype", "name", "field", "operator", "values", "action"]
    template_name = "core/autoapprovalrule_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.project = self.project
        return form

    def get_success_url(self):
        return reverse_lazy("core:autoapprovalrules", kwargs={"project": self.project.pk})


class AutoApprovalRuleUpdateView(LoginRequiredMixin, ProjectRequiredMixin, UpdateView):
    model = AutoApprovalRule
    fields = ["entitytype", "name", "field", "operator", "values", "action"]
    template_name = "core/autoapprovalrule_form.html"

    def get_queryset(self):
        return super().get_queryset().filter(project=self.project)

    def get_success_url(self):
        return reverse_lazy("core:autoapprovalrules", kwargs={"project": self.project.pk})


class AutoApprovalRuleRunNowView(LoginRequiredMixin, ProjectRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        rule = get_object_or_404(AutoApprovalRule, pk=kwargs["pk"], project=self.project)

        run_auto_approval_rule.delay(rule.pk)
        messages.success(request, _('Running "%(name)s" now.') % {"name": rule.name})

        return redirect("core:autoapprovalrules", project=self.project.pk)


class AutoApprovalRuleDeleteView(LoginRequiredMixin, ProjectRequiredMixin, DeleteView):
    model = AutoApprovalRule
    template_name = "core/autoapprovalrule_delete.html"

    def get_queryset(self):
        return super().get_queryset().filter(project=self.project)

    def get_success_url(self):
        return reverse_lazy("core:autoapprovalrules", kwargs={"project": self.project.pk})
