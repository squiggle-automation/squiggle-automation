from django.db import models
from django.utils.translation import gettext_lazy as _


# NOTE: this model is edited via both a web form (fields=[...] on ContainerCreateView/
# ContainerUpdateView in core/views/container.py) and an API serializer
# (api/serializers/container.py). If you add, remove, or rename a field, update both.
class Container(models.Model):
    class Meta:
        ordering = ["name"]

    name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        unique=True,
        verbose_name=_("Name"),
        help_text=_("Name for this configuration, not the full container name"),
    )

    image = models.CharField(
        max_length=1024,
        blank=False,
        null=False,
        verbose_name=_("Container image"),
    )

    image_tag = models.CharField(
        max_length=1024,
        default="latest",
        blank=False,
        null=False,
        verbose_name=_("Container tag"),
    )

    cap_net_raw = models.BooleanField(
        default=False,
        verbose_name=_("Allow to use RAW and PACKET sockets"),
    )

    net_host = models.BooleanField(
        default=False, verbose_name=_("Use host network"), help_text=_("Disabled network namespace of container")
    )

    configoptions = models.ManyToManyField(
        "ConfigOption",
        blank=True,
        verbose_name=_("Config options"),
    )

    def __str__(self):
        return self.name
