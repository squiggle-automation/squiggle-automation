from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View
from rest_framework.authtoken.models import Token


def mask_key(key):
    return f"{key[:3]}{'•' * (len(key) - 6)}{key[-3:]}"


class ApiTokenView(LoginRequiredMixin, TemplateView):
    """Shows the current user's API token (there is at most one, masked) - create/delete are separate views."""

    template_name = "management/apitoken.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # OneToOneField reverse accessor: raises AttributeError (via RelatedObjectDoesNotExist)
        # if unset, so getattr with a default works
        token = getattr(self.request.user, "auth_token", None)
        context["token"] = token
        context["masked_key"] = mask_key(token.key) if token else None
        return context


class ApiTokenCreateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if hasattr(request.user, "auth_token"):
            messages.error(request, _("You already have an API token. Delete it first to create a new one."))
        else:
            token = Token.objects.create(user=request.user)
            messages.success(
                request, _("Your new API token: %(key)s (this will not be shown again)") % {"key": token.key}
            )
        return redirect(reverse_lazy("management:apitoken"))


class ApiTokenDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        Token.objects.filter(user=request.user).delete()
        messages.success(request, _("API token deleted."))
        return redirect(reverse_lazy("management:apitoken"))
