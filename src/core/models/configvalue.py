from django.db import models
from django.utils.translation import gettext_lazy as _


class ConfigValue(models.Model):
    class Meta:
        ordering = ["option", "executor"]
        unique_together = ["option", "executor"]

    option = models.ForeignKey(
        "ConfigOption",
        on_delete=models.CASCADE,
        verbose_name=_("Config option"),
    )

    executor = models.ForeignKey(
        "Executor",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name=_("Executor"),
        help_text=_("If executor is not set, this is the global config"),
    )

    value = models.CharField(
        max_length=10000,
        blank=False,
        null=False,
        verbose_name=_("Value"),
    )

    def __str__(self):
        scope = "Global"
        if self.executor:
            scope = self.executor.name
        return f"{self.option.name} - {scope}"
