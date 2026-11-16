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
from .mixins import HtmxPartialMixin, ProjectRequiredMixin, QueryUrlMixin


class ExecutionListView(LoginRequiredMixin, ProjectRequiredMixin, HtmxPartialMixin, QueryUrlMixin, ListView):
    """
    List of the executions of the project.

    Works like the entity list (see EntityListView), just with fixed columns. The whole query is
    kept in the url, so that a filtered list can be linked and bookmarked:
        ?s=<column>     sort ascending by a column, "?s=-<column>" for descending
        ?q=<term>       search for a substring of the executor name, or for the execution id
        ?state=<state>  filter for one Execution state
    """

    context_object_name = "executions"
    template_name = "core/execution_list.html"
    partial_template_name = "core/execution_list_content.html"
    paginate_by = 100

    # element htmx replaces when the sorting or filtering changes (see execution_list.html)
    htmx_target = "#execution-list"

    # the sortable columns: name in "?s=<name>" -> (header label, model field to order by)
    sort_columns = {
        "executor": (_("Executor"), "executor__name"),
        "state": (_("State"), "state"),
        "created_at": (_("Created at"), "created_at"),
    }

    # newest first, as long as nothing else is picked
    default_sort = ("created_at", True)

    def get_queryset(self):
        queryset = Execution.objects.filter(project=self.project).select_related("executor")

        self.search_term = self.request.GET.get("q", "").strip()
        if self.search_term:
            queryset = queryset.filter(self.get_search_condition(self.search_term))

        self.state_filter = self.get_state_filter()
        if self.state_filter is not None:
            queryset = queryset.filter(state=self.state_filter)

        self.sort_key, self.sort_descending = self.get_sort()
        field = self.sort_columns[self.sort_key][1]

        return queryset.annotate(
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
        ).order_by(
            f"-{field}" if self.sort_descending else field,
            # tiebreaker: rows with the same executor/state would otherwise come in an undefined
            # order, so a row could show up on two pages, or on none. newest first among them
            "-pk",
        )

    def get_search_condition(self, term):
        """
        A substring of the executor name, or - if the term is a number - the id of the execution
        (which is not a column, but shows up in the url of the details page).
        """
        condition = Q(executor__name__icontains=term)

        # isdecimal() rather than isdigit(): the latter is also true for e.g. "²", which int()
        # rejects. an id beyond the range of the column just matches nothing
        if term.isdecimal():
            condition |= Q(pk=int(term))

        return condition

    def get_state_filter(self):
        """The Execution state to filter for, picked with "?state=<state>", or None for all states."""
        try:
            state = int(self.request.GET.get("state", ""))
        except ValueError:
            return None

        return state if state in Execution.STATE_CHOICES else None

    def get_sort(self):
        """
        The column to sort by and whether it is descending, picked with "?s=<column>" /
        "?s=-<column>". An unknown column falls back to the default sorting rather than being
        rejected.
        """
        value = self.request.GET.get("s", "")
        descending = value.startswith("-")
        key = value.removeprefix("-")

        if key not in self.sort_columns:
            return self.default_sort

        return key, descending

    def get_sort_headers(self):
        """
        The header of every sortable column, by column name: its label, the url that sorts by
        it, and how it is sorted at the moment.
        """
        headers = {}

        for key, (label, _field) in self.sort_columns.items():
            active = key == self.sort_key

            # clicking the column that is already sorted by flips the direction, any other
            # column starts ascending
            descending = active and not self.sort_descending

            headers[key] = {
                "label": label,
                "sorted": active,
                "descending": active and self.sort_descending,
                "url": self.build_query_url(single={"s": f"-{key}" if descending else key}),
            }

        return headers

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["list_htmx_target"] = self.htmx_target

        context["sort_key"] = self.sort_key
        context["sort_descending"] = self.sort_descending
        context["sort_headers"] = self.get_sort_headers()

        context["search_term"] = self.search_term
        context["state_filter"] = self.state_filter
        context["state_choices"] = Execution.STATE_CHOICES.items()
        context["filters_active"] = bool(self.search_term or self.state_filter is not None)
        # drops every filter, but keeps the sorting
        context["clear_filters_url"] = self.build_query_url(single={"q": None, "state": None})

        return context


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
