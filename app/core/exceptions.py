"""Custom domain and infrastructure exceptions for HookRelay."""


class HookRelayException(Exception):
    """Base exception for all HookRelay application errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(HookRelayException):
    """Raised when application configuration is missing or invalid."""


class DatabaseConnectionError(HookRelayException):
    """Raised when database connectivity fails."""


class InfrastructureError(HookRelayException):
    """Raised when external infrastructure (e.g. Redis) is unavailable."""
