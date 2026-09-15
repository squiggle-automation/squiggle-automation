from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .container import Container
from .entitytype import EntityType


# NOTE: this model is edited via both a web form (fields=[...] on ExecutorCreateView/
# ExecutorUpdateView in core/views/executor.py) and an API serializer
# (api/serializers/executor.py). If you add, remove, or rename a field, update both.
class Executor(models.Model):
    class Meta:
        ordering = ["name"]

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        verbose_name=_("Name"),
    )

    container = models.ForeignKey(
        Container,
        on_delete=models.CASCADE,
        verbose_name=_("Executor container"),
    )

    input = models.ManyToManyField(
        EntityType,
        related_name="executor_input",
        blank=True,
    )

    output = models.ManyToManyField(
        EntityType,
        related_name="executor_output",
        blank=True,
    )

    max_entities = models.PositiveIntegerField(
        null=False,
        default=100,
        validators=[MinValueValidator(1)],
        verbose_name=_("Maximal number of entities grouped into one execution"),
    )

    max_entities_timeout = models.PositiveIntegerField(
        null=False,
        default=5,
        verbose_name=_("Waiting time in minutes until execution is scheduled if not enough entities are found"),
    )

    workerprofile = models.ForeignKey(
        "WorkerProfile",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Worker profile for this execution"),
    )

    keep_tmp_files = models.BooleanField(
        default=False,
        verbose_name=_("Keep temporary files after execution"),
        help_text=_(
            "Do not delete the input, output and temporary files after the execution finished. Useful for debugging executors."
        ),
    )

    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
    )

    def __str__(self):
        return self.name
