import os
from types import SimpleNamespace
from unittest import mock

import docker
from django.conf import settings
from django.test import TestCase, override_settings

from ..exceptions import ExecutionRuntimeError
from ..models import (
    SENSITIVE_VALUE_MASK,
    ConfigOption,
    ConfigValue,
    Container,
    Executor,
)
from ..tasks.run_executor import _get_configuration, _run_container


class GetConfigurationTests(TestCase):
    def setUp(self):
        self.container = Container.objects.create(name="container", image="image")
        self.executor = Executor.objects.create(name="executor", container=self.container)

    def test_resolves_plain_and_sensitive_values(self):
        plain_option = ConfigOption.objects.create(name="plain-option", sensitive=False)
        sensitive_option = ConfigOption.objects.create(name="secret-option", sensitive=True)
        self.container.configoptions.set([plain_option, sensitive_option])

        ConfigValue.objects.create(option=plain_option, executor=self.executor, value="plain-value")
        ConfigValue.objects.create(option=sensitive_option, executor=self.executor, value="topsecret")

        configuration, masked_configuration = _get_configuration(self.executor)

        self.assertEqual(configuration["plain-option"], "plain-value")
        self.assertEqual(configuration["secret-option"], "topsecret")

        self.assertEqual(masked_configuration["plain-option"], "plain-value")
        self.assertEqual(masked_configuration["secret-option"], SENSITIVE_VALUE_MASK)

    def test_falls_back_to_global_default_value(self):
        option = ConfigOption.objects.create(name="opt")
        self.container.configoptions.set([option])
        ConfigValue.objects.create(option=option, executor=None, value="global-default")

        configuration, masked_configuration = _get_configuration(self.executor)

        self.assertEqual(configuration["opt"], "global-default")
        self.assertEqual(masked_configuration["opt"], "global-default")

    def test_unset_option_resolves_to_none_and_is_not_masked(self):
        sensitive_option = ConfigOption.objects.create(name="secret-option", sensitive=True)
        self.container.configoptions.set([sensitive_option])

        configuration, masked_configuration = _get_configuration(self.executor)

        self.assertIsNone(configuration["secret-option"])
        # no value was ever set, so there is nothing sensitive to mask
        self.assertIsNone(masked_configuration["secret-option"])

    def test_executor_value_overrides_global_default(self):
        option = ConfigOption.objects.create(name="opt")
        self.container.configoptions.set([option])
        ConfigValue.objects.create(option=option, executor=None, value="global-default")
        ConfigValue.objects.create(option=option, executor=self.executor, value="executor-specific")

        configuration, _ = _get_configuration(self.executor)

        self.assertEqual(configuration["opt"], "executor-specific")


class RunContainerTests(TestCase):
    def setUp(self):
        self.container = Container.objects.create(name="container", image="image")
        self.execution = SimpleNamespace(id=1, executor=SimpleNamespace(name="executor"))

    def run_container(self):
        with mock.patch("core.tasks.run_executor.docker.from_env") as from_env:
            _run_container(
                self.execution,
                self.container,
                os.path.join(settings.ARTIFACTS_DIR, "artifacts"),
                os.path.join(settings.TMP_DIR, "input"),
                os.path.join(settings.TMP_DIR, "output"),
                os.path.join(settings.TMP_DIR, "tmp"),
            )
        return from_env.return_value.containers.run.call_args.kwargs

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=[])
    def test_no_mounts_by_default(self):
        # containers without mounts also run if mounts are disabled
        kwargs = self.run_container()

        self.assertEqual(kwargs["mounts"], [])

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_mounts_are_read_only_binds(self):
        self.container.mounts = {"/srv/wordlists": "/data/wordlists", "/srv/secrets.yaml": "/opt/secrets.yaml"}

        kwargs = self.run_container()

        self.assertEqual(
            kwargs["mounts"],
            [
                docker.types.Mount(target="/data/wordlists", source="/srv/wordlists", type="bind", read_only=True),
                docker.types.Mount(target="/opt/secrets.yaml", source="/srv/secrets.yaml", type="bind", read_only=True),
            ],
        )
        # the platform's own directories are still mounted
        self.assertEqual(
            {v["bind"] for v in kwargs["volumes"].values()},
            {"/data/artifacts", "/data/input", "/data/output", "/data/tmp"},
        )

    @override_settings(CONTAINER_MOUNT_ALLOWED_HOST_PATHS=["/srv/"])
    def test_invalid_mounts_are_not_run(self):
        # e.g. saved before the allowed host paths were restricted, or changed without clean() -
        # the rules themselves are tested with Container.validate_mounts()
        self.container.mounts = {"/srv/wordlists": "/data/wordlists", "/etc": "/data/etc"}

        with mock.patch("core.tasks.run_executor.docker.from_env") as from_env:
            with self.assertRaisesMessage(
                ExecutionRuntimeError, 'invalid mounts: "/etc" is not below an allowed host path (/srv/).'
            ):
                _run_container(self.execution, self.container, "artifacts", "input", "output", "tmp")

        from_env.return_value.containers.run.assert_not_called()
