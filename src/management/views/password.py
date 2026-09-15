from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView as DjangoPasswordChangeView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


class PasswordChangeView(LoginRequiredMixin, DjangoPasswordChangeView):
    """Lets a logged in user change their own password."""

    template_name = "management/password_change.html"
    success_url = reverse_lazy("core:start")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Password changed successfully."))
        return response
