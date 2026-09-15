import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import celeryd_init, task_failure
from django.conf import settings
from django.db import DatabaseError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "squiggle_automation.settings")

app = Celery("squiggle_automation")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs):
    # note: exceptions in this code are not displayed in celery
    # for debugging, add own exception handling that prints all exceptions
    #
    # additionally, django is not fully loaded here. importing models will fail
    try:
        from core.tasks import run_event_handler

        sender.add_periodic_task(crontab(), run_event_handler.s())
    except Exception as e:
        print(f"ERROR during setup of periodic tasks (setup_periodic_tasks): {e}")


@task_failure.connect
def celery_error_handler(task_id, exception, traceback, einfo, *args, **kwargs):
    if settings.DEBUG:
        return

    # TODO: log error somewhere


@celeryd_init.connect
def configure_workers(sender=None, conf=None, options=None, instance=None, **kwargs):
    # get queue name from options
    queues = options.get("queues")
    if queues is None:
        return

    if len(queues) != 1:
        print(f"Error: Expected exactly one queue to be provided, got {len(queues)}: {queues}")
        raise SystemExit(1)
    queue = queues[0]

    # get worker configuration
    from core.models import WorkerProfile

    try:
        worker = WorkerProfile.objects.get(name=queue)
    except WorkerProfile.DoesNotExist:
        print(f'Error: No worker configuration found for "{queue}"')
        raise SystemExit(1)
    except DatabaseError as e:
        # Celery ignores this exception, if we do not raise the SystemExit
        # This happens if the database is not setup properly yet (down, migrations running, ...)
        print(f'Error: Could not query worker configuration for "{queue}": {e}')
        raise SystemExit(1)

    # set concurrency
    conf.worker_concurrency = worker.concurrency
