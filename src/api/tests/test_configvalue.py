from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import (
    SENSITIVE_VALUE_MASK,
    ConfigOption,
    ConfigValue,
    Container,
    Executor,
)
from squiggle_automation.testutils import random_password

User = get_user_model()


class ConfigOptionValueApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.option = ConfigOption.objects.create(name="opt")
        self.sensitive_option = ConfigOption.objects.create(name="secret-opt", sensitive=True)

    def _url(self, option):
        return reverse("api:configoption-value", args=[option.name])

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(self._url(self.option))
        self.assertEqual(r.status_code, 401)

    def test_get_unset_value_is_null(self):
        r = self.client.get(self._url(self.option))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["value"])

    def test_get_plain_value(self):
        ConfigValue.objects.create(option=self.option, executor=None, value="hello")

        r = self.client.get(self._url(self.option))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["value"], "hello")

    def test_get_sensitive_value_is_masked(self):
        ConfigValue.objects.create(option=self.sensitive_option, executor=None, value="topsecret")

        r = self.client.get(self._url(self.sensitive_option))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["value"], SENSITIVE_VALUE_MASK)
        self.assertNotIn("topsecret", r.content.decode())

    def test_put_sets_value(self):
        r = self.client.put(self._url(self.option), {"value": "new-value"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["value"], "new-value")

        configvalue = ConfigValue.objects.get(option=self.option, executor=None)
        self.assertEqual(configvalue.value, "new-value")

    def test_put_sensitive_value_returns_masked_response_but_stores_real_value(self):
        r = self.client.put(self._url(self.sensitive_option), {"value": "topsecret"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["value"], SENSITIVE_VALUE_MASK)
        self.assertNotIn("topsecret", r.content.decode())

        configvalue = ConfigValue.objects.get(option=self.sensitive_option, executor=None)
        self.assertEqual(configvalue.value, "topsecret")

    def test_put_null_clears_existing_value(self):
        ConfigValue.objects.create(option=self.option, executor=None, value="hello")

        r = self.client.put(self._url(self.option), {"value": None}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.data["value"])
        self.assertFalse(ConfigValue.objects.filter(option=self.option, executor=None).exists())

    def test_put_empty_string_clears_existing_value(self):
        ConfigValue.objects.create(option=self.option, executor=None, value="hello")

        r = self.client.put(self._url(self.option), {"value": ""}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(ConfigValue.objects.filter(option=self.option, executor=None).exists())

    def test_put_does_not_affect_executor_specific_value(self):
        container = Container.objects.create(name="container", image="alpine")
        container.configoptions.add(self.option)
        executor = Executor.objects.create(name="executor", container=container)
        ConfigValue.objects.create(option=self.option, executor=executor, value="executor-value")

        r = self.client.put(self._url(self.option), {"value": "global-value"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        executor_value = ConfigValue.objects.get(option=self.option, executor=executor)
        self.assertEqual(executor_value.value, "executor-value")


class ExecutorConfigApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("apiuser2", password=random_password())
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.container = Container.objects.create(name="container", image="alpine")
        self.option_a = ConfigOption.objects.create(name="opt-a")
        self.option_b = ConfigOption.objects.create(name="opt-b", sensitive=True)
        self.container.configoptions.set([self.option_a, self.option_b])
        self.executor = Executor.objects.create(name="executor", container=self.container)

    def _url(self):
        return reverse("api:executor-config", args=[self.executor.name])

    def test_unauthenticated_request_is_rejected(self):
        anon_client = APIClient()
        r = anon_client.get(self._url())
        self.assertEqual(r.status_code, 401)

    def test_get_returns_all_relevant_options_unset(self):
        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"opt-a": None, "opt-b": None})

    def test_get_masks_sensitive_and_shows_plain_values(self):
        ConfigValue.objects.create(option=self.option_a, executor=self.executor, value="plain")
        ConfigValue.objects.create(option=self.option_b, executor=self.executor, value="topsecret")

        r = self.client.get(self._url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["opt-a"], "plain")
        self.assertEqual(r.data["opt-b"], SENSITIVE_VALUE_MASK)
        self.assertNotIn("topsecret", r.content.decode())

    def test_get_ignores_global_default_shows_only_executor_override(self):
        # mirrors the web UI's ExecutorConfigView: this endpoint is about the executor-specific
        # override, not the effective (fallback-inclusive) value used at execution time
        ConfigValue.objects.create(option=self.option_a, executor=None, value="global-default")

        r = self.client.get(self._url())
        self.assertIsNone(r.data["opt-a"])

    def test_put_sets_some_values_only(self):
        r = self.client.put(self._url(), {"opt-a": "value-a"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["opt-a"], "value-a")
        self.assertIsNone(r.data["opt-b"])

        self.assertEqual(ConfigValue.objects.get(option=self.option_a, executor=self.executor).value, "value-a")
        self.assertFalse(ConfigValue.objects.filter(option=self.option_b, executor=self.executor).exists())

    def test_put_sets_all_values(self):
        r = self.client.put(self._url(), {"opt-a": "value-a", "opt-b": "value-b"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        self.assertEqual(ConfigValue.objects.get(option=self.option_a, executor=self.executor).value, "value-a")
        self.assertEqual(ConfigValue.objects.get(option=self.option_b, executor=self.executor).value, "value-b")

    def test_patch_clears_one_value_leaving_others_untouched(self):
        ConfigValue.objects.create(option=self.option_a, executor=self.executor, value="value-a")
        ConfigValue.objects.create(option=self.option_b, executor=self.executor, value="value-b")

        r = self.client.patch(self._url(), {"opt-a": None}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        self.assertFalse(ConfigValue.objects.filter(option=self.option_a, executor=self.executor).exists())
        self.assertEqual(ConfigValue.objects.get(option=self.option_b, executor=self.executor).value, "value-b")

    def test_put_unknown_option_name_is_rejected(self):
        r = self.client.put(self._url(), {"does-not-exist": "value"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ConfigValue.objects.filter(executor=self.executor).exists())

    def test_put_non_string_value_is_rejected(self):
        r = self.client.put(self._url(), {"opt-a": 123}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ConfigValue.objects.filter(option=self.option_a, executor=self.executor).exists())

    def test_put_non_object_body_is_rejected(self):
        r = self.client.put(self._url(), ["not", "an", "object"], format="json")
        self.assertEqual(r.status_code, 400)
