class ConfigurationError(ValueError):
    """Raised when required application settings are missing or invalid."""


class GitLabAPIError(RuntimeError):
    """Raised when GitLab API requests fail or return invalid payloads."""


class LLMInvocationError(RuntimeError):
    """Raised when LLM invocation fails or returns malformed output."""
