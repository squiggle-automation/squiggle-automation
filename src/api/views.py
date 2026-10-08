from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from core.models import (
    AutoApprovalRule,
    ConfigOption,
    Container,
    Entity,
    EntityType,
    Executor,
    Project,
    WorkerProfile,
)

from .serializers import (
    AutoApprovalRuleSerializer,
    ConfigOptionSerializer,
    ConfigValueSerializer,
    ContainerSerializer,
    EntitySerializer,
    EntityTypeSerializer,
    ExecutorSerializer,
    ProjectSerializer,
    WorkerProfileSerializer,
)
from .serializers.entity import STATE_NAMES
from .utils import masked_configvalue, set_configvalue


class ProjectScopedViewSetMixin:
    """
    For a ModelViewSet whose URL is nested under /projects/<project>/... (see api/urls.py) -
    filters the queryset to that project and injects it on create. The API equivalent of
    core.views.mixins.ProjectRequiredMixin: a request for a nonexistent project 404s, for every
    action.
    """

    def get_project(self):
        return get_object_or_404(Project, pk=self.kwargs["project"])

    def get_queryset(self):
        return super().get_queryset().filter(project=self.get_project())

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class AutoApprovalRuleViewSet(ProjectScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = AutoApprovalRule.objects.all()
    serializer_class = AutoApprovalRuleSerializer
    lookup_field = "name"


class EntityView(ProjectScopedViewSetMixin, generics.GenericAPIView):
    """
    GET returns the entities of one entity type in one project, PUT imports (creates or updates) a single one.

    Entities are identified by the identifier keys in their data, so there is no detail URL - PUT is an upserts operation instead.
    """

    queryset = Entity.objects.all()
    serializer_class = EntitySerializer
    # no queryset-based filtering/pagination here - GET returns a plain list, see get()
    # TODO: add pagination
    pagination_class = None

    @extend_schema(
        parameters=[OpenApiParameter("state", enum=list(STATE_NAMES.values()), required=False)],
        responses=EntitySerializer(many=True),
    )
    def get(self, request, project, entitytype):
        entitytype = get_object_or_404(EntityType, name=entitytype)

        # get_queryset() is already limited to the project of the URL
        entities = self.get_queryset().filter(entitytype=entitytype)

        state = request.query_params.get("state")
        if state is not None:
            states_by_name = {name: value for value, name in STATE_NAMES.items()}
            if state not in states_by_name:
                raise DRFValidationError({"state": f"Unknown state, must be one of: {', '.join(states_by_name)}"})
            entities = entities.filter(state=states_by_name[state])

        entities = entities.order_entity_by_values(entitytype)
        return Response(EntitySerializer(entities, many=True).data)

    @extend_schema(request=EntitySerializer, responses={200: EntitySerializer, 201: EntitySerializer})
    def put(self, request, project, entitytype):
        project = self.get_project()
        entitytype = get_object_or_404(EntityType, name=entitytype)

        # the serializer validates the data against the schema of the entity type
        serializer = EntitySerializer(data=request.data, context={"entitytype": entitytype})
        serializer.is_valid(raise_exception=True)

        entity, created = Entity.objects.upsert_entity(entitytype, project, serializer.validated_data["data"])
        return Response(
            EntitySerializer(entity).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class EntityTypeViewSet(viewsets.ModelViewSet):
    queryset = EntityType.objects.all()
    serializer_class = EntityTypeSerializer
    lookup_field = "name"


class ConfigOptionViewSet(viewsets.ModelViewSet):
    queryset = ConfigOption.objects.all()
    serializer_class = ConfigOptionSerializer
    lookup_field = "name"

    @action(detail=True, methods=["get", "put"])
    def value(self, request, name=None):
        """The global (executor=None) value of this config option."""
        option = self.get_object()

        if request.method == "PUT":
            serializer = ConfigValueSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            set_configvalue(option, None, serializer.validated_data["value"])

        configvalue = option.get_default_value()
        return Response({"value": masked_configvalue(option, configvalue)})


class ContainerViewSet(viewsets.ModelViewSet):
    queryset = Container.objects.all()
    serializer_class = ContainerSerializer
    lookup_field = "name"


class ExecutorViewSet(viewsets.ModelViewSet):
    queryset = Executor.objects.all()
    serializer_class = ExecutorSerializer
    lookup_field = "name"

    @action(detail=True, methods=["get", "put", "patch"])
    def config(self, request, name=None):
        """
        All config values relevant to this executor (i.e. its container's config options),
        as {option_name: value}. GET always returns all of them; PUT/PATCH accept a partial or
        full mapping - only the given keys are changed, a null value clears that one.
        """
        executor = self.get_object()
        options_by_name = {option.name: option for option in executor.container.configoptions.all()}

        if request.method in ("PUT", "PATCH"):
            if not isinstance(request.data, dict):
                raise DRFValidationError("expected an object mapping config option names to values")

            unknown = set(request.data) - set(options_by_name)
            if unknown:
                raise DRFValidationError(
                    {option_name: "not a config option of this executor's container" for option_name in unknown}
                )

            errors = {
                option_name: "must be a string or null"
                for option_name, value in request.data.items()
                if value is not None and not isinstance(value, str)
            }
            if errors:
                raise DRFValidationError(errors)

            with transaction.atomic():
                for option_name, value in request.data.items():
                    set_configvalue(options_by_name[option_name], executor, value)

        data = {
            option.name: masked_configvalue(option, option.get_value(executor, no_default=True))
            for option in options_by_name.values()
        }
        return Response(data)


class WorkerProfileViewSet(viewsets.ModelViewSet):
    queryset = WorkerProfile.objects.all()
    serializer_class = WorkerProfileSerializer
    lookup_field = "name"

    def perform_destroy(self, instance):
        # WorkerProfile.delete() raises a plain django ValidationError (not a DRF one) if this
        # is the default worker - translate it so it comes back as 400, not an unhandled 500
        try:
            instance.delete()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)
