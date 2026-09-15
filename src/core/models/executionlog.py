from django.db import models
from django.utils.translation import gettext_lazy as _


class ExecutionLog(models.Model):
    class Meta:
        ordering = ["-created_at"]

    LEVEL_ERROR = 1
    LEVEL_WARNING = 2
    LEVEL_INFO = 3
    LEVEL_SCHEDULER = 4

    LEVEL_CHOICES = {
        LEVEL_ERROR: _("Error"),
        LEVEL_WARNING: _("Warning"),
        LEVEL_INFO: _("Info"),
        LEVEL_SCHEDULER: _("Scheduler"),
    }

    execution = models.ForeignKey(
        "Execution",
        on_delete=models.CASCADE,
        verbose_name=_("Execution"),
    )

    level = models.IntegerField(
        choices=LEVEL_CHOICES,
        verbose_name=_("Level"),
    )

    message = models.TextField(
        max_length=10000,
        blank=True,
        null=False,
        verbose_name=_("Message"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created at"),
        help_text=_("Timestamp when log was added (usually later than the event happened)"),
    )

    def __str__(self):
        return f"{self.execution} - {self.level} -  {self.message[:50]}"
