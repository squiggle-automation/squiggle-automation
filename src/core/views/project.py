from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from ..forms import ProjectSwitchForm
from ..models import Project
from .mixins import ProjectOptionalMixin


class ProjectListView(LoginRequiredMixin, ProjectOptionalMixin, ListView):
    model = Project
    context_object_name = "projects"
    template_name = "core/project_list.html"
    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # add switch forms to project objects
        for p in context["projects"]:
            p.switch_form = ProjectSwitchForm(p)

        return context


class ProjectCreateView(LoginRequiredMixin, ProjectOptionalMixin, CreateView):
    model = Project
    fields = ["name", "run_executors"]
    template_name = "core/project_form.html"
    success_url = reverse_lazy("core:projects")


class ProjectUpdateView(LoginRequiredMixin, ProjectOptionalMixin, UpdateView):
    model = Project
    fields = ["name", "run_executors"]
    template_name = "core/project_form.html"
    success_url = reverse_lazy("core:projects")


class ProjectDeleteView(LoginRequiredMixin, ProjectOptionalMixin, DeleteView):
    model = Project
    template_name = "core/project_delete.html"
    success_url = reverse_lazy("core:projects")


class ProjectSwitchView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        project_id = request.POST.get("project")

        # get project to verify that it is valid
        project = get_object_or_404(Project, pk=project_id)

        # store the project in the sessions
        request.session["active_project_id"] = project.pk

        return redirect("core:entities", project=project.pk)
