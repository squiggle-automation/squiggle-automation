from django.urls import path
from django.views.generic.base import RedirectView

from .models import Entity
from .views import (
    AutoApprovalRuleCreateView,
    AutoApprovalRuleDeleteView,
    AutoApprovalRuleListView,
    AutoApprovalRuleRunNowView,
    AutoApprovalRuleUpdateView,
    ConfigOptionCreateView,
    ConfigOptionDeleteView,
    ConfigOptionListView,
    ConfigOptionUpdateView,
    ContainerCreateView,
    ContainerDeleteView,
    ContainerListView,
    ContainerUpdateView,
    EntityCreateView,
    EntityDeleteView,
    EntityListView,
    EntityOverviewView,
    EntityStateChangeView,
    EntityTypeCreateView,
    EntityTypeDeleteView,
    EntityTypeListView,
    EntityTypeUpdateView,
    EntityUpdateView,
    ExecutionArtifactDownloadView,
    ExecutionDetailView,
    ExecutionInputEntitiesView,
    ExecutionListView,
    ExecutionRetryAllView,
    ExecutionRetryView,
    ExecutorConfigView,
    ExecutorCreateView,
    ExecutorDeleteView,
    ExecutorListView,
    ExecutorRunAllEntitiesView,
    ExecutorUpdateView,
    ProjectCreateView,
    ProjectDeleteView,
    ProjectListView,
    ProjectSwitchView,
    ProjectUpdateView,
    WorkerProfileCreateView,
    WorkerProfileDeleteView,
    WorkerProfileListView,
    WorkerProfileUpdateView,
)

app_name = "core"

urlpatterns = [
    # we dont have a main landing page (yet?) - redirect to projects
    path("", RedirectView.as_view(url="projects"), name="start"),
    # project
    path("projects/", ProjectListView.as_view(), name="projects"),
    path("projects/create/", ProjectCreateView.as_view(), name="project-create"),
    path("projects/<int:pk>/", ProjectUpdateView.as_view(), name="project-update"),
    path("projects/<int:pk>/delete/", ProjectDeleteView.as_view(), name="project-delete"),
    # switch project
    path("projects/switch/", ProjectSwitchView.as_view(), name="project-switch"),
    # entitytypes (global)
    path("entitytypes/", EntityTypeListView.as_view(), name="entitytypes"),
    path("entitytypes/create/", EntityTypeCreateView.as_view(), name="entitytype-create"),
    path("entitytypes/<int:pk>/", EntityTypeUpdateView.as_view(), name="entitytype-update"),
    path("entitytypes/<int:pk>/delete/", EntityTypeDeleteView.as_view(), name="entitytype-delete"),
    # configoptions (global)
    path("configoptions/", ConfigOptionListView.as_view(), name="configoptions"),
    path("configoptions/create/", ConfigOptionCreateView.as_view(), name="configoption-create"),
    path("configoptions/<int:pk>/", ConfigOptionUpdateView.as_view(), name="configoption-update"),
    path("configoptions/<int:pk>/delete/", ConfigOptionDeleteView.as_view(), name="configoption-delete"),
    # containers (global)
    path("containers/", ContainerListView.as_view(), name="containers"),
    path("containers/create/", ContainerCreateView.as_view(), name="container-create"),
    path("containers/<int:pk>/", ContainerUpdateView.as_view(), name="container-update"),
    path("containers/<int:pk>/delete/", ContainerDeleteView.as_view(), name="container-delete"),
    # executors (global)
    path("executors/", ExecutorListView.as_view(), name="executors"),
    path("executors/create/", ExecutorCreateView.as_view(), name="executor-create"),
    path("executors/<int:pk>/", ExecutorUpdateView.as_view(), name="executor-update"),
    path("executors/<int:pk>/values/", ExecutorConfigView.as_view(), name="executor-config"),
    path(
        "executors/<int:pk>/run/",
        ExecutorRunAllEntitiesView.as_view(),
        name="executor-run-all-entities",
    ),
    path("executors/<int:pk>/delete/", ExecutorDeleteView.as_view(), name="executor-delete"),
    # worker profiles (global)
    path("workerprofiles/", WorkerProfileListView.as_view(), name="workerprofiles"),
    path("workerprofiles/create/", WorkerProfileCreateView.as_view(), name="workerprofile-create"),
    path("workerprofiles/<int:pk>/", WorkerProfileUpdateView.as_view(), name="workerprofile-update"),
    path("workerprofiles/<int:pk>/delete/", WorkerProfileDeleteView.as_view(), name="workerprofile-delete"),
    # entities (project scoped)
    path("p/<int:project>/entities/", EntityOverviewView.as_view(), name="entities"),
    path("p/<int:project>/entities/<str:entitytype>", EntityListView.as_view(), name="entity-list"),
    path("p/<int:project>/entities/create/<str:entitytype>/", EntityCreateView.as_view(), name="entity-create"),
    path("p/<int:project>/entities/<int:pk>/", EntityUpdateView.as_view(), name="entity-update"),
    path(
        "p/<int:project>/entities/<int:pk>/approve/",
        EntityStateChangeView.as_view(new_state=Entity.STATE_ENABLED),
        name="entity-approve",
    ),
    path(
        "p/<int:project>/entities/<int:pk>/decline/",
        EntityStateChangeView.as_view(new_state=Entity.STATE_DISABLED),
        name="entity-decline",
    ),
    path(
        "p/<int:project>/entities/<int:pk>/reprocess/",
        EntityStateChangeView.as_view(),
        name="entity-reprocess",
    ),
    path("p/<int:project>/entities/<int:pk>/delete/", EntityDeleteView.as_view(), name="entity-delete"),
    # auto approval rules (project scoped)
    path("p/<int:project>/autoapprovalrules/", AutoApprovalRuleListView.as_view(), name="autoapprovalrules"),
    path(
        "p/<int:project>/autoapprovalrules/create/",
        AutoApprovalRuleCreateView.as_view(),
        name="autoapprovalrule-create",
    ),
    path(
        "p/<int:project>/autoapprovalrules/<int:pk>/",
        AutoApprovalRuleUpdateView.as_view(),
        name="autoapprovalrule-update",
    ),
    path(
        "p/<int:project>/autoapprovalrules/<int:pk>/delete/",
        AutoApprovalRuleDeleteView.as_view(),
        name="autoapprovalrule-delete",
    ),
    path(
        "p/<int:project>/autoapprovalrules/<int:pk>/run/",
        AutoApprovalRuleRunNowView.as_view(),
        name="autoapprovalrule-run",
    ),
    # executions (project scoped)
    path("p/<int:project>/executions/", ExecutionListView.as_view(), name="executions"),
    path("p/<int:project>/executions/<int:pk>/", ExecutionDetailView.as_view(), name="execution-details"),
    path(
        "p/<int:project>/executions/<int:pk>/entities/",
        ExecutionInputEntitiesView.as_view(),
        name="execution-input-entities",
    ),
    path(
        "p/<int:project>/executions/<int:pk>/artifacts/<str:filename>/",
        ExecutionArtifactDownloadView.as_view(),
        name="execution-artifact-download",
    ),
    path("p/<int:project>/executions/<int:pk>/retry/", ExecutionRetryView.as_view(), name="execution-retry"),
    path("p/<int:project>/executions/retryall/", ExecutionRetryAllView.as_view(), name="execution-retry-all"),
]
