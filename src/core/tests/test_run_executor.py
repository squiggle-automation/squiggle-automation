from django.test import TestCase

from ..models import (
    SENSITIVE_VALUE_MASK,
    ConfigOption,
    ConfigValue,
    Container,
    Executor,
)
from ..tasks.run_executor import _get_configuration


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
