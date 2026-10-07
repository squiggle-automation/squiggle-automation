from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AutoApprovalRuleViewSet,
    ConfigOptionViewSet,
    ContainerViewSet,
    EntityTypeViewSet,
    EntityView,
    ExecutorViewSet,
    ProjectViewSet,
    WorkerProfileViewSet,
)

app_name = "api"

v1_router = DefaultRouter()
v1_router.register("projects", ProjectViewSet, basename="project")
v1_router.register("entitytypes", EntityTypeViewSet, basename="entitytype")
v1_router.register("configoptions", ConfigOptionViewSet, basename="configoption")
v1_router.register("containers", ContainerViewSet, basename="container")
v1_router.register("executors", ExecutorViewSet, basename="executor")
v1_router.register("workerprofiles", WorkerProfileViewSet, basename="workerprofile")

urlpatterns = [
    path("v1/", include(v1_router.urls)),
    # auto approval rules are scoped to their project via the URL rather than a router-registered
    # flat resource - same names (autoapprovalrule-list/-detail) a router would have generated
    path(
        "v1/projects/<int:project>/autoapprovalrules/",
        AutoApprovalRuleViewSet.as_view({"get": "list", "post": "create"}),
        name="autoapprovalrule-list",
    ),
    path(
        "v1/projects/<int:project>/autoapprovalrules/<int:pk>/",
        AutoApprovalRuleViewSet.as_view(
            {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
        ),
        name="autoapprovalrule-detail",
    ),
    # entities are scoped to their project and entity type via the URL, and identified by the
    # identifier keys in their data - hence only a collection URL (GET to export, PUT to import)
    path(
        "v1/projects/<int:project>/entities/<str:entitytype>/",
        EntityView.as_view(),
        name="entity-list",
    ),
]
