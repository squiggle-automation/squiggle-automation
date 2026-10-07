import os

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView

from ..exceptions import ExecutionAbortError, ExecutionRetryError
from ..models import Execution, ExecutionLog
from .mixins import ProjectRequiredMixin


class ExecutionListView(LoginRequiredMixin, ProjectRequiredMixin, ListView):
    context_object_name = "executions"
    template_name = "core/execution_list.html"
    paginate_by = 100

    def get_queryset(self):
        return (
            Execution.objects.filter(project=self.project)
            .select_related("executor")
            .annotate(
                error_count=Count(
                    "executionlog",
                    filter=Q(executionlog__level=ExecutionLog.LEVEL_ERROR),
                ),
                warning_count=Count(
                    "executionlog",
                    filter=Q(executionlog__level=ExecutionLog.LEVEL_WARNING),
                ),
                info_count=Count(
                    "executionlog",
                    filter=Q(executionlog__level=ExecutionLog.LEVEL_INFO),
                ),
                total_logs=Count("executionlog"),
            )
            .order_by("-created_at")
        )


class ExecutionDetailView(LoginRequiredMixin, ProjectRequiredMixin, DetailView):
    context_object_name = "execution"
    template_name = "core/execution_detail.html"
    artifacts_limit = 20

    def get_queryset(self):
        return Execution.objects.filter(project=self.project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["logs"] = self.object.get_log()
        context["artifacts"], context["artifacts_limit_reached"] = self.object.artifact_files(
            limit=self.artifacts_limit
        )

        return context


class ExecutionInputEntitiesView(LoginRequiredMixin, ProjectRequiredMixin, ListView):
    context_object_name = "entities"
    template_name = "core/execution_input_entities.html"
    paginate_by = 100

    def get_queryset(self):
        self.execution = get_object_or_404(Execution, pk=self.kwargs["pk"], project=self.project)
        return self.execution.entities.select_related("entitytype").order_by("entitytype__name", "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["execution"] = self.execution
        return context


class ExecutionArtifactDownloadView(LoginRequiredMixin, ProjectRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        execution = get_object_or_404(Execution, pk=kwargs["pk"], project=self.project)

        # only allow downloading files that are actually listed in the artifact directory, this
        # also rules out path traversal via the filename
        filename = kwargs["filename"]
        artifact_files, _ = execution.artifact_files()
        if filename not in artifact_files:
            raise Http404

        file_path = os.path.join(execution.artifact_directory, filename)
        return FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename)


class ExecutionRetryView(LoginRequiredMixin, ProjectRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        execution_id = kwargs.get("pk")
        execution = get_object_or_404(Execution, pk=execution_id, project=self.project)
        try:
            execution.retry()
        except ExecutionRetryError:
            messages.error(request, _("Execution cannot be retried because it did not fail"))

        return redirect("core:execution-details", project=self.project.pk, pk=execution.id)


class ExecutionRetryAllView(LoginRequiredMixin, ProjectRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        executions = Execution.objects.filter(project=self.project, state=Execution.STATE_FAILED)
        for execution in executions:
            try:
                execution.retry()
            except ExecutionRetryError:
                # maybe the state changed between in between - ignore it
                pass

        return redirect("core:executions", project=self.project.pk)


class ExecutionAbortView(LoginRequiredMixin, ProjectRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        execution = get_object_or_404(Execution, pk=kwargs.get("pk"), project=self.project)
        try:
            execution.abort()
        except ExecutionAbortError:
            messages.error(request, _("Execution cannot be aborted because it is not in an allowed state for that"))

        return redirect("core:execution-details", project=self.project.pk, pk=execution.id)
