from django import forms
from django.utils.translation import gettext_lazy as _

from ..models import ConfigValue


class ConfigValueForm(forms.ModelForm):
    class Meta:
        model = ConfigValue
        fields = ["value"]

    clear = forms.BooleanField(
        required=False,
        label=_("Clear value"),
    )

    def __init__(self, *args, **kwargs):
        self.configoption = kwargs.pop("configoption")
        self.executor = kwargs.pop("executor")

        super().__init__(*args, **kwargs)

        # allow empty values - empty means delete
        self.fields["value"].required = False
        # do not show a label
        self.fields["value"].label = False
        # show the configoption's description as help text instead
        self.fields["value"].help_text = self.configoption.description

        # if sensitive, use a PasswordInput that does not leak the value
        self._sensitive = self.configoption.sensitive
        self._old_value = self.instance.value
        if self._sensitive:
            self.fields["value"].widget = forms.PasswordInput(
                render_value=False,
                attrs={"placeholder": _("Leave blank to keep the current value")},
            )
        else:
            # otherwise, we do not need the "clear" checkbox because an empty value means delete
            del self.fields["clear"]

    def save(self, commit=True):
        """Save the object. If the value is empty, delete it."""
        instance = super().save(commit=False)

        # delete the value? yes if:
        # not sensitive: it is empty
        # sensitive: clear is set
        if (not self._sensitive and not instance.value) or (self._sensitive and self.cleaned_data.get("clear")):
            if instance.pk:
                instance.delete()
            return

        # no value -> get the old one (it is sensitive, otherwise the deletion would be triggered)
        if not instance.value:
            instance.value = self._old_value

        # we still do not have a value? abort, do not save
        if not instance.value:
            return

        # now everything is fine, save
        instance.option = self.configoption
        instance.executor = self.executor
        if commit:
            instance.save()
        return instance
