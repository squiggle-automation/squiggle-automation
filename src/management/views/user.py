from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import CreateView, DeleteView, FormView, UpdateView

from squiggle_automation.utils import SuperuserRequiredMixing

from ..forms import UserCreateForm

User = get_user_model()


class UserListView(SuperuserRequiredMixing, ListView):
    model = User
    context_object_name = "users"
    ordering = ["username"]
    template_name = "management/user_list.html"

    def get_queryset(self):
        # avoids one extra query per row to check for an api token (see user_list.html)
        return super().get_queryset().select_related("auth_token")


class UserCreateView(SuperuserRequiredMixing, CreateView):
    model = User
    form_class = UserCreateForm  # we need this to handle the password correctly
    template_name = "management/user_form.html"
    success_url = reverse_lazy("management:users")


class UserUpdateView(SuperuserRequiredMixing, UpdateView):
    model = User
    fields = ["username", "first_name", "last_name", "email", "is_active", "is_superuser"]
    template_name = "management/user_form.html"
    success_url = reverse_lazy("management:users")


class UserPasswordResetView(SuperuserRequiredMixing, SingleObjectMixin, FormView):
    model = User
    form_class = SetPasswordForm
    template_name = "management/user_password_reset.html"
    success_url = reverse_lazy("management:users")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_form_kwargs(self):
        # SetPasswordForm is not a ModelForm, it takes the user as its own "user" kwarg
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.object
        return kwargs

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class UserDeleteView(SuperuserRequiredMixing, DeleteView):
    model = User
    template_name = "management/user_delete.html"
    success_url = reverse_lazy("management:users")
