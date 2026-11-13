from django.core import checks
from django.test import SimpleTestCase, override_settings

from ..checks import check_container_mount_allowed_host_paths


class ContainerMountAllowedHostPathsCheckTests(SimpleTestCase):
    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=[])
    def test_warns_if_unset(self):
        messages = check_container_mount_allowed_host_paths(None)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level, checks.WARNING)
        self.assertEqual(messages[0].id, "core.W001")
        self.assertIn("CONTAINER_MOUNT_ALLOWED_HOST_PATHS is not set", messages[0].msg)

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_no_warning_if_set(self):
        self.assertEqual(check_container_mount_allowed_host_paths(None), [])

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=[])
    def test_is_registered(self):
        ids = [m.id for m in checks.run_checks()]
        self.assertIn("core.W001", ids)
