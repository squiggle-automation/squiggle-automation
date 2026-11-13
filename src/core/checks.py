from django.conf import settings
from django.core.checks import Info, register


# also called by the celery workers on startup
@register()
def check_container_mount_allowed_host_paths(app_configs, **kwargs):
    if settings.CONTAINER_MOUNT_ALLOWED_HOST_PATHS:
        return []

    return [
        Info(
            "CONTAINER_MOUNT_ALLOWED_HOST_PATHS is not set - mounting host paths into executor containers is disabled",
            hint='Set it to the host paths that may be mounted (comma separated, e.g. "/srv/") to use container mounts.',
            id="core.I001",
        )
    ]
