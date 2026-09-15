from django.db import models
from django.utils.translation import gettext_lazy as _

from .configvalue import ConfigValue

# placeholder returned instead of the actual value of a sensitive config option
SENSITIVE_VALUE_MASK = "***"


# NOTE: this model is edited via both a web form (fields=[...] on ConfigOptionCreateView/
# ConfigOptionUpdateView in core/views/configoption.py) and an API serializer
# (api/serializers/configoption.py). If you add, remove, or rename a field, update both.
class ConfigOption(models.Model):
    class Meta:
        ordering = ["name"]

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        verbose_name=_("Name"),
        help_text=_("Name for this configuration option"),
    )

    description = models.CharField(
        max_length=1000,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Shown as help text when setting a value for this option"),
    )

    sensitive = models.BooleanField(
        default=False,
        verbose_name=_("Sensitive"),
        help_text=_(
            'Sensitive values are not displayed (Note: Do not rely on this - you can obtain a sensitive value by disabling the "sensitive" flag)'
        ),
    )

    def __str__(self):
        return self.name

    def get_value(self, executor=None, no_default=False):
        """Gets the value of this option.

        If executor is set, the applicable value for the executor is returned.
        If it is not set, the default value is returned (unless no_default is set).
        None is returned if no value is set at all.
        """
        # try to find value for the executor
        if executor:
            try:
                return ConfigValue.objects.get(option=self, executor=executor)
            except ConfigValue.DoesNotExist:
                if no_default:
                    return None

        # otherwise use the default
        return self.get_default_value()

    def get_default_value(self):
        try:
            return ConfigValue.objects.get(option=self, executor__isnull=True)
        except ConfigValue.DoesNotExist:
            pass
