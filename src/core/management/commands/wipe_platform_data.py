from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    ConfigOption,
    ConfigValue,
    Container,
    EntityType,
    Execution,
    Executor,
    Project,
    WorkerProfile,
)

# Order matters only for how readable the per-step counts below are - Django's delete()
# resolves the full downstream cascade for each queryset regardless of call order, so this is
# not required for correctness. Entity, Event and ExecutionLog are not listed explicitly: all
# three cascade-delete automatically (Entity/Event via EntityType and Project, ExecutionLog via
# Execution), so they end up empty too without needing their own step.
MODELS = [Execution, ConfigValue, Executor, Container, EntityType, ConfigOption, WorkerProfile, Project]


class Command(BaseCommand):
    help = (
        "Delete ALL EntityTypes, Containers, Executors, ConfigOptions, ConfigValues, "
        "WorkerProfiles, Projects and Executions - i.e. the entire platform configuration and "
        "collected data. Entities, Events and ExecutionLogs are removed too, as a side effect "
        "of cascading deletes. Users/auth data is not touched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="do not prompt for confirmation",
        )

    def handle(self, *args, **options):
        if options["interactive"]:
            self.stdout.write(self.style.WARNING(self.help))
            answer = input('\nType "yes" to continue, or anything else to cancel: ')
            if answer != "yes":
                self.stdout.write("cancelled")
                return

        with transaction.atomic():
            for model in MODELS:
                total, _ = model.objects.all().delete()
                self.stdout.write(f"{model.__name__}: deleted {total}")

        self.stdout.write(self.style.SUCCESS("done"))
