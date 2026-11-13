from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings

from core.models import WorkerProfile

from ..celery import configure_workers


class _Conf:
    worker_concurrency = None


class ConfigureWorkersTests(TestCase):
    def test_no_queues_does_nothing(self):
        conf = _Conf()
        configure_workers(conf=conf, options={"queues": None})
        self.assertIsNone(conf.worker_concurrency)

    def test_multiple_queues_exits(self):
        conf = _Conf()
        with self.assertRaises(SystemExit) as cm:
            configure_workers(conf=conf, options={"queues": ["low", "medium"]})
        self.assertEqual(cm.exception.code, 1)

    def test_unknown_worker_exits(self):
        conf = _Conf()
        with self.assertRaises(SystemExit) as cm:
            configure_workers(conf=conf, options={"queues": ["missing"]})
        self.assertEqual(cm.exception.code, 1)

    def test_database_error_exits_instead_of_being_swallowed(self):
        # Regression test: previously only WorkerProfile.DoesNotExist was caught, so a
        # DatabaseError (e.g. raised because the database has not been migrated yet,
        # which happens when a worker container races the app container's migrations
        # on a fresh `docker-compose up`) propagated out of this signal receiver
        # uncaught. Celery's signal dispatcher swallows any exception that isn't a
        # SystemExit without crashing the worker, so the worker silently started up
        # with the wrong (default) configuration instead of crashing as intended.
        conf = _Conf()
        with patch.object(WorkerProfile.objects, "get", side_effect=DatabaseError("relation does not exist")):
            with self.assertRaises(SystemExit) as cm:
                configure_workers(conf=conf, options={"queues": ["medium"]})
        self.assertEqual(cm.exception.code, 1)

    def test_known_worker_sets_concurrency(self):
        WorkerProfile.objects.create(name="medium", concurrency=7)
        conf = _Conf()
        configure_workers(conf=conf, options={"queues": ["medium"]})
        self.assertEqual(conf.worker_concurrency, 7)

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=[])
    def test_info_if_mount_allowed_host_paths_are_unset(self):
        WorkerProfile.objects.create(name="medium", concurrency=7)
        with patch("builtins.print") as print_mock:
            configure_workers(conf=_Conf(), options={"queues": ["medium"]})
        print_mock.assert_called_once_with(
            "Info: CONTAINER_MOUNT_ALLOWED_HOST_PATHS is not set - mounting host paths into executor containers "
            "is disabled"
        )

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_no_info_if_mount_allowed_host_paths_are_set(self):
        WorkerProfile.objects.create(name="medium", concurrency=7)
        with patch("builtins.print") as print_mock:
            configure_workers(conf=_Conf(), options={"queues": ["medium"]})
        print_mock.assert_not_called()
