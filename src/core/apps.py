from django.apps import AppConfig


class DatamodelConfig(AppConfig):
    name = "core"

    def ready(self):
        # registers the system checks
        from . import checks  # noqa: F401
