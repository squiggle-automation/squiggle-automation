"""
Shared helpers for reading/writing ConfigValue entries via the API - used by both the global
config endpoint (ConfigOptionViewSet.value) and the per-executor one (ExecutorViewSet.config).
"""

from core.models import SENSITIVE_VALUE_MASK, ConfigValue


def masked_configvalue(option, configvalue):
    """The value to expose in an API response: masked if the option is sensitive, None if unset."""
    if configvalue is None:
        return None
    if option.sensitive:
        return SENSITIVE_VALUE_MASK
    return configvalue.value


def set_configvalue(option, executor, value):
    """
    Set the ConfigValue for (option, executor) to value, or clear/delete it if value is empty/None.

    Unlike the web UI's ConfigValueForm (which needs a "blank means unchanged" workaround because
    an HTML password input can't re-render the current value), a JSON API has no such ambiguity:
    omit the key to leave a value untouched, send null/"" to clear it.
    """
    if not value:
        ConfigValue.objects.filter(option=option, executor=executor).delete()
        return None

    configvalue, _ = ConfigValue.objects.update_or_create(option=option, executor=executor, defaults={"value": value})
    return configvalue
