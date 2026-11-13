import posixpath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

# container paths the platform mounts into every executor container - additional mounts must not shadow them
RESERVED_CONTAINER_PATHS = ["/data/artifacts", "/data/input", "/data/output", "/data/tmp"]


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

    mounts = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Mounts"),
        help_text=_(
            'Host directories or files mounted read-only into the container, as JSON object {"<host path>": '
            '"<container path>"}, e.g. {"/srv/wordlists": "/data/wordlists"}. Host paths are paths on the Docker '
            "host and must exist."
        ),
    )

    configoptions = models.ManyToManyField(
        "ConfigOption",
        blank=True,
        verbose_name=_("Config options"),
    )

    def __str__(self):
        return self.name

    def clean(self):
        # an emptied form field arrives as None
        if self.mounts is None:
            self.mounts = {}

        self.validate_mounts()

    def validate_mounts(self):
        """
        Checks all mount rules and raises a ValidationError for "mounts" with every problem found.

        Called by clean() when the container is saved via form/API/admin, and again before the
        container is run - as containers might be changed without clean() (e.g. shell, DB) and
        CONTAINER_MOUNT_ALLOWED_HOST_PATHS might be restricted after a container was saved.
        """
        if not isinstance(self.mounts, dict):
            raise ValidationError({"mounts": _('Mounts must be a JSON object {"<host path>": "<container path>"}.')})

        errors = []
        if self.mounts and not settings.CONTAINER_MOUNT_ALLOWED_HOST_PATHS:
            errors.append(_("Mounts are disabled, as CONTAINER_MOUNT_ALLOWED_HOST_PATHS is not set."))

        container_paths = []
        for host_path, container_path in self.mounts.items():
            if not isinstance(container_path, str):
                errors.append(_("Container paths must be strings."))
                continue

            invalid_paths = [
                path
                for path in (host_path, container_path)
                # ":" is the separator in Docker's bind syntax, ".." would make the path ambiguous
                if not path.startswith("/") or ":" in path or ".." in path.split("/")
            ]
            if invalid_paths:
                for path in invalid_paths:
                    errors.append(_('"%(path)s" must be an absolute path without ":" or "..".') % {"path": path})
                continue

            if settings.CONTAINER_MOUNT_ALLOWED_HOST_PATHS and not self._is_allowed_host_path(host_path):
                errors.append(
                    _('"%(path)s" is not below an allowed host path (%(allowed)s).')
                    % {"path": host_path, "allowed": ", ".join(settings.CONTAINER_MOUNT_ALLOWED_HOST_PATHS)}
                )

            container_path = posixpath.normpath(container_path)
            if container_path == "/":
                errors.append(_('Cannot mount to "/".'))
                continue

            for reserved in RESERVED_CONTAINER_PATHS:
                # neither the reserved directory itself, anything below it, nor a parent of it
                if (
                    container_path == reserved
                    or container_path.startswith(reserved + "/")
                    or reserved.startswith(container_path + "/")
                ):
                    errors.append(
                        _('"%(path)s" overlaps with "%(reserved)s", which is used by the platform.')
                        % {"path": container_path, "reserved": reserved}
                    )

            if container_path in container_paths:
                errors.append(_('"%(path)s" is used more than once as container path.') % {"path": container_path})
            container_paths.append(container_path)

        if errors:
            raise ValidationError({"mounts": errors})

    @staticmethod
    def _is_allowed_host_path(host_path):
        """Whether host_path is (below) one of settings.CONTAINER_MOUNT_ALLOWED_HOST_PATHS."""
        host_path = posixpath.normpath(host_path)
        for allowed_path in settings.CONTAINER_MOUNT_ALLOWED_HOST_PATHS:
            allowed_path = posixpath.normpath(allowed_path)
            # compare with a trailing separator, so that "/srv" does not allow "/srv2"
            if host_path == allowed_path or host_path.startswith(allowed_path.rstrip("/") + "/"):
                return True
        return False
