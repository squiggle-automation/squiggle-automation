from django.db import models
from django.utils.translation import gettext_lazy as _


class Event(models.Model):
    project = models.ForeignKey(
        "Project",
        on_delete=models.CASCADE,
        verbose_name=_("Project"),
    )

    entity = models.ForeignKey(
        "Entity",
        on_delete=models.CASCADE,
        verbose_name=_("Entity"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return str(self.entity)
