from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, View
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from ..forms import EntityForm
from ..models import Entity, EntityType
from .mixins import HtmxPartialMixin, ProjectRequiredMixin, QueryUrlMixin


class EntityOverviewView(LoginRequiredMixin, ProjectRequiredMixin, ListView):
    context_object_name = "entitytypes"
    template_name = "core/entity_overview.html"

    def get_queryset(self):
        entitytypes = EntityType.objects.all()

        # counts is a dict: (entitytype_id, state) -> count
        counts = {
            (entitytype_id, state): count
            for entitytype_id, state, count in (
                Entity.objects.filter(project=self.project)
                .values_list("entitytype", "state")
                .order_by("entitytype", "state")
                .annotate(count=Count("id"))
            )
        }

        for entitytype in entitytypes:
            entitytype.count_active = counts.get((entitytype.id, Entity.STATE_ENABLED), 0)
            entitytype.count_waiting = counts.get((entitytype.id, Entity.STATE_WAITING_APPROVAL), 0)
            entitytype.count_disabled = counts.get((entitytype.id, Entity.STATE_DISABLED), 0)
            entitytype.count = entitytype.count_active + entitytype.count_waiting + entitytype.count_disabled

        return entitytypes


class EntityListView(LoginRequiredMixin, ProjectRequiredMixin, HtmxPartialMixin, QueryUrlMixin, ListView):
    """
    List of the entities of one entity type.

    The columns are not fixed: an entity keeps its values in Entity.data and which keys exist
    is described per entity type by EntityType.schema, so the shown columns are chosen with
    "?c=<key>" and default to the identifier keys.

    The same goes for sorting and filtering, which is why neither is done with a library like
    django-filter: there is only one model field to work with (Entity.data), and what can be
    sorted or filtered on are the schema keys inside it, which are only known at runtime.
    The whole query is kept in the url, so that a filtered list can be linked and bookmarked:
        ?c=<key>        the shown columns (repeatable)
        ?s=<key>        sort ascending by a key, "?s=-<key>" for descending
        ?q=<term>       search for a substring in any of the schema keys
        ?f_<key>=<term> filter one column for a substring
        ?state=<state>  filter for one Entity state
    """

    context_object_name = "entities"
    template_name = "core/entity_list.html"
    partial_template_name = "core/entity_list_content.html"
    paginate_by = 100

    # element htmx replaces when the shown columns, sorting or filtering change (see entity_list.html)
    htmx_target = "#entity-list"

    # prefix of the per column filter parameters. no schema key can collide with the other
    # parameters, because a key only ever appears with this prefix in front of it
    filter_prefix = "f_"

    def get_queryset(self):
        entitytype_name = self.kwargs.get("entitytype")

        # we could also directly filter for the name, but this results in a 404 for invalid entiytypes
        self.entitytype = get_object_or_404(EntityType, name=entitytype_name)

        queryset = Entity.objects.filter(project=self.project, entitytype=self.entitytype)

        self.column_filters = self.get_column_filters()
        queryset = queryset.filter_entity_by_values(self.column_filters)

        self.search_term = self.request.GET.get("q", "").strip()
        if self.search_term:
            # searches every key of the schema, not only the shown columns - a hit in a hidden
            # column is still a hit, and hiding a column should not change what the search finds
            queryset = queryset.search_entity_values(self.entitytype.schema_keys_list, self.search_term)

        self.state_filter = self.get_state_filter()
        if self.state_filter is not None:
            queryset = queryset.filter(state=self.state_filter)

        self.sort_key, self.sort_descending = self.get_sort()

        return queryset.order_entity_by_values(
            self.entitytype,
            keys=[self.sort_key] if self.sort_key else None,
            descending=self.sort_descending,
        )

    def get_column_filters(self):
        """
        The active per column filters as a dict of key -> substring, picked with "?f_<key>=<substring>".

        Unknown keys and empty values are dropped rather than rejected, for the same reason an
        unknown column is (see get_visible_columns()) - and because the filter inputs are always
        submitted, including the empty ones.
        """
        available = self.entitytype.schema_keys_list
        filters = {}

        for name, value in self.request.GET.items():
            if not name.startswith(self.filter_prefix):
                continue

            key = name.removeprefix(self.filter_prefix)
            value = value.strip()
            if key in available and value:
                filters[key] = value

        return filters

    def get_state_filter(self):
        """The Entity state to filter for, picked with "?state=<state>", or None for all states."""
        try:
            state = int(self.request.GET.get("state", ""))
        except ValueError:
            return None

        return state if state in Entity.STATE_CHOICES else None

    def get_sort(self):
        """
        The key to sort by and whether it is descending, picked with "?s=<key>" / "?s=-<key>".

        An unknown key falls back to (None, False), i.e. to the default sorting by the
        identifier keys - like an unknown column, it is ignored rather than rejected.
        """
        value = self.request.GET.get("s", "")
        descending = value.startswith("-")
        key = value.removeprefix("-")

        if key not in self.entitytype.schema_keys_list:
            return None, False

        return key, descending

    def get_visible_columns(self):
        """
        The visible columns to show, picked with "?c=<key>" (repeatable).

        Always in schema order, so that the table looks the same however the columns were
        picked. Unknown keys are ignored rather than rejected, so an url that outlived a schema
        change still works. Without a selection the identifier keys are shown.
        """
        available = self.entitytype.schema_keys_list
        selected = set(self.request.GET.getlist("c"))

        columns = [i for i in available if i in selected]
        if not columns:
            identifier_keys = set(self.entitytype.identifier_keys_list)
            columns = [i for i in available if i in identifier_keys]

        return columns

    def get_column_picker_options(self, visible_columns):
        """
        The entries of the column picker: every available key, whether it is currently shown,
        and the url that adds or removes it.
        """
        options = []

        for key in self.entitytype.schema_keys_list:
            shown = key in visible_columns

            if shown:
                # shown -> remove it from list
                selection = [i for i in visible_columns if i != key]
            else:
                # not shown -> add it to list
                selection = visible_columns + [key]

            options.append({"key": key, "shown": shown, "url": self.build_query_url(multi={"c": selection})})

        return options

    def get_column_headers(self, visible_columns):
        """
        The header of every shown column: the url that sorts by it, how it is sorted at the
        moment, and the name/value of its filter input.
        """
        headers = []

        for key in visible_columns:
            active = key == self.sort_key

            # clicking the column that is already sorted by flips the direction, any other
            # column starts ascending
            descending = active and not self.sort_descending

            headers.append(
                {
                    "key": key,
                    "sorted": active,
                    "descending": active and self.sort_descending,
                    "url": self.build_query_url(single={"s": f"-{key}" if descending else key}),
                    "filter_name": f"{self.filter_prefix}{key}",
                    "filter_value": self.column_filters.get(key, ""),
                }
            )

        return headers

    def get_clear_filters_url(self):
        """The url that drops every filter, but keeps the shown columns and the sorting."""
        cleared = {"q": None, "state": None}
        for key in self.entitytype.schema_keys_list:
            cleared[f"{self.filter_prefix}{key}"] = None

        return self.build_query_url(single=cleared)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["entitytype"] = self.entitytype
        context["list_htmx_target"] = self.htmx_target

        columns = self.get_visible_columns()
        context["columns"] = columns
        context["column_options"] = self.get_column_picker_options(columns)
        context["column_headers"] = self.get_column_headers(columns)

        context["sort_key"] = self.sort_key
        context["sort_descending"] = self.sort_descending
        context["column_filters"] = self.column_filters
        context["search_term"] = self.search_term
        context["state_filter"] = self.state_filter
        context["state_choices"] = Entity.STATE_CHOICES.items()
        context["filters_active"] = bool(self.column_filters or self.search_term or self.state_filter is not None)
        context["clear_filters_url"] = self.get_clear_filters_url()

        # cells are precomputed here because the template cannot index entity.data with a
        # variable column key ({{ entity.data.key }} only works for a literal key)
        for entity in context[self.context_object_name]:
            # data is not necessarily an object: it is nullable and only validated when clean()
            # runs, which the raw sql of upsert_entity() does not (see Entity.identifier_value)
            data = entity.data if isinstance(entity.data, dict) else {}
            entity.cells = [data.get(key) for key in columns]

        return context


class EntityCreateView(LoginRequiredMixin, ProjectRequiredMixin, CreateView):
    model = Entity
    form_class = EntityForm
    template_name = "core/entity_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)

        entitytype_name = self.kwargs.get("entitytype")
        self.entitytype = get_object_or_404(EntityType, name=entitytype_name)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["entitytype"] = self.entitytype
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.project = self.project
        form.instance.entitytype = self.entitytype
        return form

    def get_success_url(self):
        return reverse_lazy("core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.entitytype.name})


class EntityUpdateView(LoginRequiredMixin, ProjectRequiredMixin, UpdateView):
    model = Entity
    form_class = EntityForm
    template_name = "core/entity_form.html"

    def get_queryset(self):
        return super().get_queryset().filter(project=self.project)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["entitytype"] = self.object.entitytype
        return kwargs

    def get_success_url(self):
        return reverse_lazy(
            "core:entity-list", kwargs={"project": self.project.pk, "entitytype": self.object.entitytype.name}
        )


class EntityStateChangeView(LoginRequiredMixin, ProjectRequiredMixin, View):
    """
    Changes the state of an entity, or reprocesses it if new_state is not set.

    Configured per url via as_view(new_state=...), e.g.:
        EntityStateChangeView.as_view(new_state=Entity.STATE_ENABLED)  # approve
        EntityStateChangeView.as_view(new_state=Entity.STATE_DISABLED)  # decline
        EntityStateChangeView.as_view()  # reprocess: state stays the same, just add the event again
    """

    new_state = None

    def post(self, request, *args, **kwargs):
        entity = get_object_or_404(Entity, pk=kwargs["pk"], project=self.project)

        if self.new_state is not None:
            # approve/decline: only allowed while the entity is waiting for approval
            if entity.state != Entity.STATE_WAITING_APPROVAL:
                messages.error(request, _("Entity is not waiting for approval."))
            else:
                entity.state = self.new_state
                entity.save()  # this also adds the event if the new state is STATE_ENABLED
        else:
            # reprocess: only allowed while the entity is enabled
            if entity.state != Entity.STATE_ENABLED:
                messages.error(request, _("Entity is not enabled."))
            else:
                entity.add_event()

        # carry the current filters/sort/columns (the entity list's whole state lives in its
        # querystring) back to the list, so approving/declining/reprocessing one entity does not
        # reset the view for the others
        url = reverse("core:entity-list", kwargs={"project": self.project.pk, "entitytype": entity.entitytype.name})
        query_string = request.GET.urlencode()
        if query_string:
            url = f"{url}?{query_string}"

        return redirect(url)


class EntityDeleteView(LoginRequiredMixin, ProjectRequiredMixin, DeleteView):
    model = Entity
    template_name = "core/entity_delete.html"

    def get_queryset(self):
        return super().get_queryset().filter(project=self.project)

    def get_success_url(self):
        return reverse_lazy("core:entities", kwargs={"project": self.project.pk})
