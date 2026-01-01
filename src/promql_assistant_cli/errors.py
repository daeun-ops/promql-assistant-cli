class PromQLAssistantError(Exception):
    """Base error for this package."""


class ConfigError(PromQLAssistantError):
    """Config load/parse error."""


class RuleMatchError(PromQLAssistantError):
    """No rule could match the user prompt."""


class PrometheusAPIError(PromQLAssistantError):
    """Prometheus API call failed."""


class ValidationError(PromQLAssistantError):
    """PromQL validation failed."""
