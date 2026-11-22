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


# =============================================================================
# Ingestion & Idempotency Domain Exceptions (M1 Gate 3 / HR-IDEM-001 - HR-IDEM-002)
# =============================================================================


class IdempotencyError(HookRelayException):
    """Base exception for idempotency engine errors."""

    error_code: str = "IDEMPOTENCY_ERROR"

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        if error_code is not None:
            self.error_code = error_code


class IdempotencyFingerprintMismatchError(IdempotencyError):
    """Raised when active idempotency key reused with different fingerprint (HTTP 409)."""

    error_code = "IDEMPOTENCY_KEY_FINGERPRINT_MISMATCH"

    def __init__(
        self,
        message: str = "Idempotency key reused with a different payload fingerprint.",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class PayloadTooLargeError(HookRelayException):
    """Raised when payload exceeds streaming size limit of 1 MiB (HTTP 413)."""

    error_code = "PAYLOAD_TOO_LARGE"

    def __init__(
        self,
        message: str = "Payload exceeds maximum allowed size of 1 MiB.",
    ) -> None:
        super().__init__(message)


class UnsupportedMediaTypeError(HookRelayException):
    """Raised when request has unsupported content-type or compression (HTTP 415)."""

    error_code = "UNSUPPORTED_MEDIA_TYPE"

    def __init__(
        self,
        message: str = "Unsupported Content-Type or Content-Encoding.",
    ) -> None:
        super().__init__(message)


# =============================================================================
# Canonicalization Domain Exceptions (M1 Gate 2 / HR-CANON-001 - HR-CANON-004)
# =============================================================================


class CanonicalizationError(HookRelayException):
    """Base domain exception for all canonicalization and payload validation failures."""

    error_code: str = "CANONICALIZATION_ERROR"

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        if error_code is not None:
            self.error_code = error_code


class PayloadNestingDepthExceededError(CanonicalizationError):
    """Raised when JSON nesting depth exceeds the maximum allowed limit of 32."""

    error_code = "PAYLOAD_NESTING_DEPTH_EXCEEDED"

    def __init__(
        self,
        message: str = "JSON nesting depth exceeds the maximum allowed limit of 32.",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class UnsafeIntegerRangeError(CanonicalizationError):
    """Raised when an integer token is outside the IEEE 754 safe range [-(2^53-1), 2^53-1]."""

    error_code = "UNSAFE_INTEGER_RANGE_EXCEEDED"

    def __init__(
        self,
        message: str = "Integer token value is outside the safe range [-(2^53-1), 2^53-1].",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class InvalidUnicodeSequenceError(CanonicalizationError):
    """Raised when payload contains invalid UTF-8, BOM, or lone/unpaired Unicode surrogates."""

    error_code = "INVALID_UNICODE_SEQUENCE"

    def __init__(
        self,
        message: str = (
            "Payload contains invalid UTF-8 or unassigned/lone Unicode surrogate code points."
        ),
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class NonFiniteNumericTokenError(CanonicalizationError):
    """Raised when non-finite numbers (NaN, Infinity) or numeric overflow are encountered."""

    error_code = "NON_FINITE_NUMERIC_TOKEN"

    def __init__(
        self,
        message: str = "Numeric values NaN, Infinity, and -Infinity are forbidden.",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class TopLevelObjectRequiredError(CanonicalizationError):
    """Raised when payload root is not a JSON Object."""

    error_code = "TOP_LEVEL_OBJECT_REQUIRED"

    def __init__(
        self,
        message: str = "Payload root must be a JSON Object.",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class DuplicateObjectKeyError(CanonicalizationError):
    """Raised when a JSON object contains duplicate keys after escape decoding."""

    error_code = "DUPLICATE_OBJECT_KEY"

    def __init__(
        self,
        message: str = "Duplicate object keys are not permitted.",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)


class MalformedJsonError(CanonicalizationError):
    """Raised when payload contains malformed JSON syntax."""

    error_code = "PAYLOAD_MALFORMED"

    def __init__(
        self,
        message: str = "Malformed JSON syntax.",
    ) -> None:
        super().__init__(message=message, error_code=self.error_code)
