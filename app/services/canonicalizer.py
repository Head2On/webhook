"""RFC 8785 JSON Canonicalization Scheme (JCS) engine and fingerprinting service.

This module is a pure domain component that operates strictly on byte streams
and JSON tokens, independent of HTTP transport concerns, as required by the
M1 Gate 1 Technical Contract (HR-CANON-001 through HR-CANON-005, HR-IDEM-001).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import rfc8785

from app.core.exceptions import (
    CanonicalizationError,
    DuplicateObjectKeyError,
    InvalidUnicodeSequenceError,
    MalformedJsonError,
    NonFiniteNumericTokenError,
    PayloadNestingDepthExceededError,
    TopLevelObjectRequiredError,
    UnsafeIntegerRangeError,
)

# RFC 8785 / ECMA-262 / HookRelay Boundary Constants
MAX_NESTING_DEPTH: int = 32
MAX_SAFE_INTEGER: int = 9007199254740991  # 2^53 - 1
MIN_SAFE_INTEGER: int = -9007199254740991  # -(2^53 - 1)
FINGERPRINT_PREFIX: str = "jcs-rfc8785-v1"


@dataclass(frozen=True)
class CanonicalizerResult:
    """Deterministic domain result returned by the canonicalizer engine.

    The canonicalizer engine has zero coupling to HTTP transport layers; it yields
    either a successful canonicalization with SHA-256 fingerprint or a structured
    domain error code and message.
    """

    is_ok: bool
    canonical_bytes: bytes | None = None
    fingerprint: str | None = None
    error_code: str | None = None
    details: str | None = None

    @classmethod
    def ok(cls, canonical_bytes: bytes, fingerprint: str) -> CanonicalizerResult:
        """Create a successful canonicalization result."""
        return cls(is_ok=True, canonical_bytes=canonical_bytes, fingerprint=fingerprint)

    @classmethod
    def err(cls, error_code: str, details: str) -> CanonicalizerResult:
        """Create a failed canonicalization result."""
        return cls(is_ok=False, error_code=error_code, details=details)


def compute_fingerprint(canonical_bytes: bytes) -> str:
    """Calculate the cryptographic SHA-256 fingerprint for canonical bytes.

    Format: `jcs-rfc8785-v1:<64 lowercase hexadecimal characters>`
    Total length: exactly 79 characters.
    """
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    return f"{FINGERPRINT_PREFIX}:{digest}"


def canonicalize_rfc8785(data: Any) -> bytes:
    """Perform pure RFC 8785 JSON Canonicalization Scheme (JCS) serialization.

    Accepts any arbitrary JSON-compatible Python data structure (objects, arrays,
    primitives) and produces canonical UTF-8 bytes.
    """
    try:
        return rfc8785.dumps(data)
    except rfc8785.IntegerDomainError as e:
        raise UnsafeIntegerRangeError(str(e)) from e
    except rfc8785.FloatDomainError as e:
        raise NonFiniteNumericTokenError(str(e)) from e
    except rfc8785.CanonicalizationError as e:
        raise CanonicalizationError(str(e)) from e


def _validate_lexical_structure(text: str) -> None:
    """Perform SAX-style token scan to enforce boundary conditions before tree allocation.

    Enforces:
    - Root object requirement (REQ-INGEST-01)
    - Maximum nesting depth of 32 (HR-CANON-001)
    - Unicode surrogate pair validity (HR-CANON-003)
    - Unescaped control character prohibition
    - Single root container without trailing data
    """
    i = 0
    n = len(text)

    # 1. Skip leading insignificant whitespace
    while i < n and text[i] in " \t\n\r":
        i += 1

    if i >= n:
        raise MalformedJsonError("Payload is empty.")

    # 2. Check root token is an Object
    if text[i] != "{":
        raise TopLevelObjectRequiredError("Payload root must be a JSON Object.")

    depth = 0
    in_string = False
    escape = False

    while i < n:
        c = text[i]

        if in_string:
            if escape:
                if c == "u":
                    if i + 4 >= n:
                        raise MalformedJsonError("Truncated unicode escape sequence in string.")
                    hex_str = text[i + 1 : i + 5]
                    try:
                        cp = int(hex_str, 16)
                    except ValueError as e:
                        raise MalformedJsonError(
                            f"Invalid hexadecimal digits in unicode escape: \\u{hex_str}"
                        ) from e

                    # Validate surrogate code points (U+D800 - U+DFFF)
                    if 0xD800 <= cp <= 0xDBFF:
                        # High surrogate: must be immediately followed by \uDC00-\uDFFF
                        if i + 10 < n and text[i + 5 : i + 7] == "\\u":
                            low_hex = text[i + 7 : i + 11]
                            try:
                                low_cp = int(low_hex, 16)
                            except ValueError as e:
                                raise InvalidUnicodeSequenceError(
                                    "Invalid low surrogate escape sequence."
                                ) from e

                            if 0xDC00 <= low_cp <= 0xDFFF:
                                # Valid surrogate pair: advance past the low surrogate escape
                                i += 10
                                escape = False
                                i += 1
                                continue
                            else:
                                raise InvalidUnicodeSequenceError(
                                    "High Unicode surrogate is not followed by a valid "
                                    "low surrogate."
                                )
                        else:
                            raise InvalidUnicodeSequenceError(
                                "Payload contains lone or unpaired high Unicode "
                                "surrogate code point."
                            )
                    elif 0xDC00 <= cp <= 0xDFFF:
                        raise InvalidUnicodeSequenceError(
                            "Payload contains lone low Unicode surrogate code point."
                        )

                    i += 4
                elif c not in '"\\/bfnrt':
                    raise MalformedJsonError(f"Invalid escape sequence '\\{c}' in string literal.")
                escape = False
            else:
                if c == "\\":
                    escape = True
                elif c == '"':
                    in_string = False
                elif ord(c) < 0x20:
                    raise MalformedJsonError(
                        f"Unescaped control character 0x{ord(c):02x} in string literal."
                    )
        else:
            if c == '"':
                in_string = True
            elif c in "{[":
                depth += 1
                if depth > MAX_NESTING_DEPTH:
                    raise PayloadNestingDepthExceededError(
                        "JSON nesting depth exceeds the maximum allowed limit of 32."
                    )
            elif c in "}]":
                depth -= 1
                if depth < 0:
                    raise MalformedJsonError("Mismatched closing bracket or brace in JSON.")
                if depth == 0:
                    # Root object closed: verify all remaining characters are only whitespace
                    j = i + 1
                    while j < n and text[j] in " \t\n\r":
                        j += 1
                    if j < n:
                        raise MalformedJsonError(
                            "Unexpected trailing characters found after root JSON Object."
                        )
                    return

        i += 1

    if depth != 0 or in_string:
        raise MalformedJsonError("Unterminated JSON container or string literal.")


def validate_and_parse_payload(payload_bytes: bytes) -> dict[str, Any]:
    """Validate raw payload bytes against HookRelay ingestion boundaries and parse safely.

    Validates:
    - Byte stream input type
    - Byte Order Mark (BOM) prohibition
    - Strict UTF-8 decoding
    - Streaming lexical depth and surrogate checks
    - Duplicate key detection after escape decoding
    - Safe integer range [-(2^53-1), 2^53-1]
    - Non-finite numeric tokens (NaN, Infinity, 1e400 overflow)
    - Root JSON Object requirement
    """
    if not isinstance(payload_bytes, bytes):
        raise TypeError(f"Payload must be bytes, got {type(payload_bytes).__name__}")

    # 1. Reject leading Byte Order Mark (BOM)
    if payload_bytes.startswith(b"\xef\xbb\xbf"):
        raise InvalidUnicodeSequenceError(
            "Payload contains prohibited UTF-8 Byte Order Mark (BOM)."
        )

    # 2. Strict UTF-8 decoding
    try:
        text = payload_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InvalidUnicodeSequenceError(
            f"Payload contains invalid UTF-8 octet sequence: {e}"
        ) from e

    # 3. Lexical pre-scan for depth, surrogates, and root structure
    _validate_lexical_structure(text)

    # 4. Parsing hooks for duplicate keys and number range checks
    def _object_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen_keys: set[str] = set()
        for key, _ in pairs:
            if key in seen_keys:
                raise DuplicateObjectKeyError(
                    f"Duplicate object key '{key}' detected after escape decoding."
                )
            seen_keys.add(key)
        return dict(pairs)

    def _parse_int(token: str) -> int:
        # Lexical guard: safe ints [-9007199254740991, +9007199254740991] have <=16 digits.
        # Any token with >16 digits (excluding sign) is guaranteed outside safe range.
        # This safely rejects oversized integer tokens (e.g. > 4300 digits) without calling
        # int(token), avoiding CPU waste and preventing int_max_str_digits ValueError.
        digits = token[1:] if token.startswith(("-", "+")) else token
        stripped_digits = digits.lstrip("0") or "0"
        if len(stripped_digits) > 16:
            raise UnsafeIntegerRangeError(
                f"Integer token value '{token[:32]}...' is outside safe range [-(2^53-1), 2^53-1]."
            )

        try:
            val = int(token)
        except ValueError as e:
            # Trap any Python integer conversion limit or malformed integer representation
            raise UnsafeIntegerRangeError(
                f"Integer token value '{token[:32]}' cannot be safely parsed: {e}"
            ) from e

        if val > MAX_SAFE_INTEGER or val < MIN_SAFE_INTEGER:
            raise UnsafeIntegerRangeError(
                f"Integer token value '{token}' is outside the safe range [-(2^53-1), 2^53-1]."
            )
        return val

    def _parse_float(token: str) -> float:
        try:
            val = float(token)
        except ValueError as e:
            raise MalformedJsonError(f"Malformed numeric literal: {token}") from e
        if math.isinf(val) or math.isnan(val):
            raise NonFiniteNumericTokenError(
                f"Numeric token '{token}' resolves to non-finite or overflow value."
            )
        return val

    def _parse_constant(token: str) -> Any:
        raise NonFiniteNumericTokenError(
            f"Numeric values NaN, Infinity, and -Infinity are forbidden: '{token}'."
        )

    try:
        parsed: Any = json.loads(
            text,
            object_pairs_hook=_object_pairs_hook,
            parse_int=_parse_int,
            parse_float=_parse_float,
            parse_constant=_parse_constant,
        )
    except json.JSONDecodeError as e:
        raise MalformedJsonError(f"Malformed JSON syntax: {e}") from e

    if not isinstance(parsed, dict):
        raise TopLevelObjectRequiredError("Payload root must be a JSON Object.")

    return parsed


def canonicalize(payload_bytes: bytes) -> tuple[bytes, str]:
    """Canonicalize raw payload bytes and generate SHA-256 fingerprint.

    Returns:
        tuple[bytes, str]: A pair containing:
            1. Deterministic canonical UTF-8 JSON bytes (RFC 8785)
            2. Canonical fingerprint in format `jcs-rfc8785-v1:<64-hex-digits>`

    Raises:
        CanonicalizationError: Any domain validation or canonicalization error.
    """
    parsed = validate_and_parse_payload(payload_bytes)
    canonical_bytes = canonicalize_rfc8785(parsed)
    fingerprint = compute_fingerprint(canonical_bytes)
    return canonical_bytes, fingerprint


def canonicalize_payload(payload_bytes: bytes) -> CanonicalizerResult:
    """Canonicalize raw payload bytes and return a structured CanonicalizerResult.

    This function does not raise CanonicalizationError; it captures domain failures
    into a structured CanonicalizerResult.err object for transport layer mapping.
    """
    try:
        canonical_bytes, fingerprint = canonicalize(payload_bytes)
        return CanonicalizerResult.ok(canonical_bytes, fingerprint)
    except CanonicalizationError as e:
        return CanonicalizerResult.err(e.error_code, str(e.message))
