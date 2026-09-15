import json

from django.core.exceptions import BadRequest
from django.shortcuts import get_object_or_404

from ..models import Project


class HtmxPartialMixin:
    """
    For a ListView: renders only partial_template_name when htmx asks for it, so that changing
    the shown columns swaps the table instead of reloading the whole page.

    The partial is used only for real htmx requests. A history restore also carries
    HX-Request, but htmx puts the response into the whole page there, so it has to be the full
    template - hence the second header check.
    """

    partial_template_name = None

    def get_template_names(self):
        if (
            self.partial_template_name
            and self.request.headers.get("HX-Request")
            and not self.request.headers.get("HX-History-Restore-Request")
        ):
            return [self.partial_template_name]

        return super().get_template_names()


class QueryUrlMixin:
    """
    For a ListView: builds urls that change single parameters of the current query, so that
    columns/sorting/filtering can be offered as plain links.

    "page" is always dropped: after changing what (or how) the list shows, the page number of
    the previous query is meaningless and would often be out of range. Empty parameters are
    dropped too - they mean nothing, and the filter inputs submit all of them, empty or not
    (see core/templates/core/entity_list_content.html), so without this every url built from
    such a request would carry them along.
    """

    def build_query_url(self, single=None, multi=None):
        """
        The current url with the given parameters replaced. "single" maps a parameter name to
        one value, "multi" maps it to a list of values. A value of None removes the parameter.
        """
        query = self.request.GET.copy()
        query.pop("page", None)

        for name, value in (single or {}).items():
            if value is None:
                query.pop(name, None)
            else:
                query[name] = value

        for name, values in (multi or {}).items():
            if values is None:
                query.pop(name, None)
            else:
                query.setlist(name, values)

        for name in list(query.keys()):
            values = [i for i in query.getlist(name) if i != ""]
            if values:
                query.setlist(name, values)
            else:
                query.pop(name, None)

        encoded = query.urlencode()

        return f"{self.request.path}?{encoded}" if encoded else self.request.path


class ApiJsonPreviewMixin:
    """
    For a ListView: attaches api_json/modal_id to every object of the current page, so the list
    template can show a "View JSON" button + modal with a copy-to-clipboard button per row (see
    core/templates/core/components/json_modal.html).

    Set api_serializer_class to the api.serializers class for this model - reusing it directly
    means the preview can never drift from what the api actually returns/accepts.
    """

    api_serializer_class = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        model_name = self.model._meta.model_name
        for obj in context[self.context_object_name]:
            obj.api_json = json.dumps(self.api_serializer_class(obj).data, indent=2)
            obj.modal_id = f"{model_name}-json-{obj.pk}"
        return context


class ProjectOptionalMixin:
    """
    ProjectOptionalMixin fetches the project from the session (if it is there)
    and stores it in self.active_project.

    Additionally, the variable "active_project" is added to the template context.

    This is used for views that do not require the project itself, but the project is used in the
    templates to build urls.
    """

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)

        project_pk = request.session.get("active_project_id")
        self.active_project = None
        if project_pk:
            try:
                self.active_project = Project.objects.get(pk=project_pk)
            except Project.DoesNotExist:
                # if an old project is set, ignore it
                pass

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_project"] = self.active_project
        return context


class ProjectRequiredMixin(ProjectOptionalMixin):
    """
    ProjectRequiredMixin fetches the project that is specified in the url parameter "project"
    and stores it in self.project.

    If a project is also stored in the session, it is compared.
    If it is not the same, return an error (so that we cannot access views of other projects before switching to it).

    Additionally, the variable "active_project" is added to the template context.
    """

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(Project, pk=kwargs["project"])

        if self.active_project is not None:
            # compare to session
            if self.project != self.active_project:
                raise BadRequest("project in URL and session do not match")
        else:
            # just set it so that it is passed to template via context (see ProjectOptionalMixin)
            self.active_project = self.project
