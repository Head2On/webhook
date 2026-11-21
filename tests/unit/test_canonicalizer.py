"""HookRelay Specific Canonicalization and Rejection Test Suite.

Verifies all mandatory HookRelay domain boundary constraints, ECMA-262 numeric
edge cases, nesting depth boundaries, Unicode surrogates, safe integer bounds,
and duplicate key detection according to:
- odin.md (Section 3.E minimum requirements)
- docs/m1/01_canonicalization_technical_contract.md
- docs/m1/03_canonicalization_test_matrix.md
"""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    DuplicateObjectKeyError,
    InvalidUnicodeSequenceError,
    MalformedJsonError,
    NonFiniteNumericTokenError,
    PayloadNestingDepthExceededError,
    TopLevelObjectRequiredError,
    UnsafeIntegerRangeError,
)
from app.services.canonicalizer import (
    MAX_SAFE_INTEGER,
    MIN_SAFE_INTEGER,
    canonicalize,
    canonicalize_payload,
    canonicalize_rfc8785,
    compute_fingerprint,
)


class TestECMA262NumericSerialization:
    """Category 4: Numeric Serialization & ECMA-262 Conformance (HR-CANON-004)."""

    def test_negative_zero_serialization(self) -> None:
        """Requirement 1: Negative zero: -0.0 -> 0 (ECMA-262 7.1.12.1)."""
        payload = b'{"val": -0.0}'
        canonical_bytes, _ = canonicalize(payload)
        assert canonical_bytes == b'{"val":0}'

        # Also verify float 0.0
        canonical_bytes_zero, _ = canonicalize(b'{"val": 0.0}')
        assert canonical_bytes_zero == b'{"val":0}'

    def test_small_decimal_transition_1e_minus_6(self) -> None:
        """Requirement 2: 1e-6 -> 0.000001 (decimal notation for >= 1e-6)."""
        payload = b'{"val": 1e-6}'
        canonical_bytes, _ = canonicalize(payload)
        assert canonical_bytes == b'{"val":0.000001}'

        payload_dec = b'{"val": 0.000001}'
        canonical_bytes_dec, _ = canonicalize(payload_dec)
        assert canonical_bytes_dec == b'{"val":0.000001}'

    def test_small_exponential_transition_1e_minus_7(self) -> None:
        """Requirement 3: 1e-7 -> 1e-7 (exponential notation for < 1e-6)."""
        payload = b'{"val": 1e-7}'
        canonical_bytes, _ = canonicalize(payload)
        assert canonical_bytes == b'{"val":1e-7}'

        payload_dec = b'{"val": 0.0000001}'
        canonical_bytes_dec, _ = canonicalize(payload_dec)
        assert canonical_bytes_dec == b'{"val":1e-7}'

    def test_trailing_zero_elimination(self) -> None:
        """1.0 -> 1 (trailing .0 omitted)."""
        payload = b'{"val": 1.0}'
        canonical_bytes, _ = canonicalize(payload)
        assert canonical_bytes == b'{"val":1}'

    def test_large_number_thresholds(self) -> None:
        """1e20 -> 100000000000000000000; 1e21 -> 1e+21."""
        payload_20 = b'{"val": 1e20}'
        canonical_bytes_20, _ = canonicalize(payload_20)
        assert canonical_bytes_20 == b'{"val":100000000000000000000}'

        payload_21 = b'{"val": 1e21}'
        canonical_bytes_21, _ = canonicalize(payload_21)
        assert canonical_bytes_21 == b'{"val":1e+21}'

    @pytest.mark.parametrize("non_finite_val", [b"NaN", b"Infinity", b"-Infinity"])
    def test_nan_and_infinity_rejection(self, non_finite_val: bytes) -> None:
        """Requirement 11: NaN and Infinity rejection."""
        payload = b'{"val": ' + non_finite_val + b"}"
        with pytest.raises(NonFiniteNumericTokenError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "NON_FINITE_NUMERIC_TOKEN"

    def test_numeric_overflow_1e400_rejection(self) -> None:
        """Requirement 12: Numeric overflow such as 1e400."""
        payload = b'{"val": 1e400}'
        with pytest.raises(NonFiniteNumericTokenError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "NON_FINITE_NUMERIC_TOKEN"


class TestSafeIntegerBoundaries:
    """Category 2: Safe Integer Boundary Enforcement (HR-CANON-002)."""

    def test_safe_integer_boundaries_pass(self) -> None:
        """Requirement 10: Safe integer boundaries pass without precision loss."""
        # 0
        canonical_bytes, _ = canonicalize(b'{"val": 0}')
        assert canonical_bytes == b'{"val":0}'

        # Max safe integer: 2^53 - 1 = 9007199254740991
        canonical_bytes_max, _ = canonicalize(f'{{"val": {MAX_SAFE_INTEGER}}}'.encode())
        assert canonical_bytes_max == f'{{"val":{MAX_SAFE_INTEGER}}}'.encode()

        # Min safe integer: -(2^53 - 1) = -9007199254740991
        canonical_bytes_min, _ = canonicalize(f'{{"val": {MIN_SAFE_INTEGER}}}'.encode())
        assert canonical_bytes_min == f'{{"val":{MIN_SAFE_INTEGER}}}'.encode()

    @pytest.mark.parametrize(
        ("unsafe_val", "desc"),
        [
            (9007199254740992, "Positive unsafe boundary: 2^53"),
            (-9007199254740992, "Negative unsafe boundary: -2^53"),
            (9223372036854775807, "64-bit integer overflow: 2^63 - 1"),
            (10**30, "Unbounded large integer string: 10^30"),
        ],
    )
    def test_unsafe_integers_rejection(self, unsafe_val: int, desc: str) -> None:
        """Requirement 10: Unsafe integers beyond ±(2^53 - 1) are rejected."""
        payload = f'{{"val": {unsafe_val}}}'.encode()
        with pytest.raises(UnsafeIntegerRangeError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "UNSAFE_INTEGER_RANGE_EXCEEDED"


class TestUnicodeAndEscaping:
    """Category 3: Unicode & Surrogate Validation (HR-CANON-003) & Escaping."""

    def test_utf16_property_sorting_including_supplementary(self) -> None:
        """Requirement 4: UTF-16 property sorting, including supplementary Unicode."""
        # Supplementary character emoji (U+1F680 🚀) encodes in UTF-16 as surrogate pair (D83D DE80)
        # Compare with BMP character 'z' (U+007A) and 'A' (U+0041)
        # In UTF-16 code units: 'A' (0x0041) < 'z' (0x007A) < '🚀' (0xD83D)
        payload = '{"z": 1, "🚀": 2, "A": 3}'.encode()
        canonical_bytes, _ = canonicalize(payload)
        # Expected key order: "A", "z", "🚀"
        assert canonical_bytes == '{"A":3,"z":1,"🚀":2}'.encode()

    def test_short_control_character_escapes(self) -> None:
        """Requirement 5: All 5 short control escapes: \\b, \\f, \\n, \\r, \\t."""
        # String containing backspace, formfeed, newline, carriage return, tab, quote, backslash
        input_dict = {
            "escapes": '\b\f\n\r\t"\\',
        }
        canonical_bytes = canonicalize_rfc8785(input_dict)
        assert canonical_bytes == b'{"escapes":"\\b\\f\\n\\r\\t\\"\\\\"}'

        # Solidus must NOT be escaped
        solidus_dict = {"path": "a/b/c"}
        assert canonicalize_rfc8785(solidus_dict) == b'{"path":"a/b/c"}'

    def test_remaining_control_character_escapes(self) -> None:
        """Requirement 6: Remaining control-character escaping \\u0000 through \\u001f."""
        # \u0000 (NULL) and \u001f (US)
        input_dict = {
            "null_byte": "\x00",
            "unit_sep": "\x1f",
            "soh": "\x01",
        }
        canonical_bytes = canonicalize_rfc8785(input_dict)
        assert b'"\\u0000"' in canonical_bytes
        assert b'"\\u001f"' in canonical_bytes
        assert b'"\\u0001"' in canonical_bytes

    @pytest.mark.parametrize(
        "surrogate_escape",
        [
            r"\uD800",  # Lone high surrogate
            r"\uDBFF",  # Lone high surrogate boundary
            r"\uDC00",  # Lone low surrogate
            r"\uDFFF",  # Lone low surrogate boundary
            r"\uDC00\uD800",  # Inverted surrogate pair (low before high)
        ],
    )
    def test_lone_and_inverted_surrogates_rejection(self, surrogate_escape: str) -> None:
        """Requirement 9: Lone and inverted Unicode surrogates are strictly rejected."""
        payload = f'{{"msg": "{surrogate_escape}"}}'.encode()
        with pytest.raises(InvalidUnicodeSequenceError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "INVALID_UNICODE_SEQUENCE"

    def test_valid_surrogate_pair_passes(self) -> None:
        """Valid surrogate pairs decoded into UTF-8 scalar values and preserved."""
        # Rocket emoji: \uD83D\uDE80 -> 🚀
        payload = b'{"msg": "\\uD83D\\uDE80"}'
        canonical_bytes, _ = canonicalize(payload)
        assert canonical_bytes == '{"msg":"🚀"}'.encode()

    @pytest.mark.parametrize(
        ("bad_bytes", "desc"),
        [
            (b'{"msg": "\xc0\xaf"}', "Overlong UTF-8: 0xC0 0xAF"),
            (b'{"msg": "\x80"}', "Orphan continuation byte: 0x80"),
            (b'{"msg": "\xf0\x90\x80"}', "Truncated 4-byte sequence: missing 4th byte"),
            (b'\xef\xbb\xbf{"msg": "hi"}', "Leading UTF-8 Byte Order Mark (BOM)"),
        ],
    )
    def test_invalid_utf8_sequences_rejection(self, bad_bytes: bytes, desc: str) -> None:
        """Requirement 8: Invalid UTF-8 sequences and BOM rejected."""
        with pytest.raises(InvalidUnicodeSequenceError) as exc_info:
            canonicalize(bad_bytes)
        assert exc_info.value.error_code == "INVALID_UNICODE_SEQUENCE"


class TestDuplicateKeysAndStructuralIntegrity:
    """Category 5: Duplicate Keys and Structural Constraints."""

    def test_duplicate_keys_literal_rejection(self) -> None:
        """Requirement 7: Duplicate JSON keys identical literals rejected."""
        payload = b'{"a": 1, "a": 2}'
        with pytest.raises(DuplicateObjectKeyError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "DUPLICATE_OBJECT_KEY"

    def test_duplicate_keys_via_escape_rejection(self) -> None:
        """Requirement 7: Duplicate JSON keys after escape decoding rejected."""
        # \u0061 resolves to 'a'
        payload = b'{"a": 1, "\\u0061": 2}'
        with pytest.raises(DuplicateObjectKeyError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "DUPLICATE_OBJECT_KEY"

    def test_nested_duplicate_keys_rejection(self) -> None:
        """Requirement 7: Duplicate keys in nested objects rejected."""
        payload = b'{"outer": {"nested": 1, "\\u006e\\u0065\\u0073\\u0074\\u0065\\u0064": 2}}'
        with pytest.raises(DuplicateObjectKeyError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "DUPLICATE_OBJECT_KEY"

    @pytest.mark.parametrize(
        "invalid_root",
        [
            b"[1, 2, 3]",
            b'"just a string"',
            b"12345",
            b"true",
            b"false",
            b"null",
        ],
    )
    def test_top_level_primitives_and_arrays_rejection(self, invalid_root: bytes) -> None:
        """Requirement 15: Top-level arrays and primitives rejected."""
        with pytest.raises(TopLevelObjectRequiredError) as exc_info:
            canonicalize(invalid_root)
        assert exc_info.value.error_code == "TOP_LEVEL_OBJECT_REQUIRED"

    def test_empty_and_nested_object_handling(self) -> None:
        """Requirement 16: Empty object and nested object handling."""
        # Empty object
        canonical_empty, fp_empty = canonicalize(b"{}")
        assert canonical_empty == b"{}"
        assert fp_empty == compute_fingerprint(b"{}")

        # Nested objects
        nested_payload = b'{"a": {}, "b": {"c": {}}}'
        canonical_nested, _ = canonicalize(nested_payload)
        assert canonical_nested == b'{"a":{},"b":{"c":{}}}'

    def test_trailing_characters_rejection(self) -> None:
        """Rejects trailing tokens after root object."""
        payload = b'{"a": 1} {"b": 2}'
        with pytest.raises(MalformedJsonError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "PAYLOAD_MALFORMED"


class TestNestingDepthLimits:
    """Category 1: JSON Nesting Depth Limits (HR-CANON-001)."""

    @staticmethod
    def _build_nested_object(depth: int) -> str:
        # Depth 1: {}
        # Depth 2: {"k": {}}
        # Depth d: {"k1": {"k2": ... {"kd": 1} ...}}
        res = "1"
        for k in range(depth, 1, -1):
            res = f'{{"k{k}": {res}}}'
        return f'{{"k1": {res}}}' if depth > 1 else "{}"

    @staticmethod
    def _build_nested_array(array_depth: int) -> str:
        # Root object {} (depth 1) + array_depth nested arrays
        inner = "1"
        for _ in range(array_depth):
            inner = f"[{inner}]"
        return f'{{"a": {inner}}}'

    def test_nesting_depth_32_accepted(self) -> None:
        """Requirement 13: Nesting depth 32 accepted (boundary pass)."""
        # Object depth 32
        d32_obj = self._build_nested_object(32).encode("utf-8")
        canonical_bytes, _ = canonicalize(d32_obj)
        assert canonical_bytes.startswith(b'{"k1":')

        # Array depth 32 (1 object + 31 arrays)
        d32_arr = self._build_nested_array(31).encode("utf-8")
        canonical_arr, _ = canonicalize(d32_arr)
        assert canonical_arr.startswith(b'{"a":')

    def test_nesting_depth_33_rejected(self) -> None:
        """Requirement 14: Nesting depth 33 rejected (boundary fail)."""
        # Object depth 33
        d33_obj = self._build_nested_object(33).encode("utf-8")
        with pytest.raises(PayloadNestingDepthExceededError) as exc_info:
            canonicalize(d33_obj)
        assert exc_info.value.error_code == "PAYLOAD_NESTING_DEPTH_EXCEEDED"

        # Array depth 33 (1 object + 32 arrays)
        d33_arr = self._build_nested_array(32).encode("utf-8")
        with pytest.raises(PayloadNestingDepthExceededError) as exc_arr:
            canonicalize(d33_arr)
        assert exc_arr.value.error_code == "PAYLOAD_NESTING_DEPTH_EXCEEDED"

    def test_alternating_nesting_depth_33_rejected(self) -> None:
        """Mixed alternating object/array nesting reaching depth 33 is rejected."""
        # Build alternating: {"k1": [{"k3": [{"k5": ...}]}]}
        # depth 1 = {
        # depth 2 = [
        # depth 3 = {
        # ...
        # depth 33 = rejected
        curr = "1"
        for i in range(33, 0, -1):
            if i % 2 == 0:
                curr = f"[{curr}]"
            else:
                curr = f'{{"k{i}": {curr}}}'
        payload = curr.encode()

        with pytest.raises(PayloadNestingDepthExceededError) as exc_info:
            canonicalize(payload)
        assert exc_info.value.error_code == "PAYLOAD_NESTING_DEPTH_EXCEEDED"


class TestFingerprintingAndDeterminism:
    """Cryptographic Fingerprint & Result Container."""

    def test_stable_fingerprints_for_equivalent_inputs(self) -> None:
        """Requirement 17: Stable fingerprints for equivalent canonical JSON inputs."""
        input_1 = b'{"b": 2, "a": 1, "c": [3, 4]}'
        input_2 = b'{\n  "c": [\n    3,\n    4\n  ],\n  "a": 1,\n  "b": 2\n}'
        input_3 = b'{"a":1,"b":2,"c":[3,4]}'

        bytes_1, fp_1 = canonicalize(input_1)
        bytes_2, fp_2 = canonicalize(input_2)
        bytes_3, fp_3 = canonicalize(input_3)

        assert bytes_1 == bytes_2 == bytes_3 == b'{"a":1,"b":2,"c":[3,4]}'
        assert fp_1 == fp_2 == fp_3
        assert fp_1.startswith("jcs-rfc8785-v1:")
        assert len(fp_1) == 79

    def test_different_payloads_produce_different_fingerprints(self) -> None:
        """Requirement 18: Different canonical payloads producing different fingerprints."""
        _, fp_1 = canonicalize(b'{"a": 1}')
        _, fp_2 = canonicalize(b'{"a": 2}')
        _, fp_3 = canonicalize(b'{"b": 1}')

        assert fp_1 != fp_2
        assert fp_2 != fp_3
        assert fp_1 != fp_3

    def test_canonicalize_payload_result_object_success_and_error(self) -> None:
        """Validates CanonicalizerResult contract for success and failure."""
        # Success case
        res_ok = canonicalize_payload(b'{"valid": true}')
        assert res_ok.is_ok is True
        assert res_ok.canonical_bytes == b'{"valid":true}'
        assert res_ok.fingerprint is not None
        assert res_ok.fingerprint.startswith("jcs-rfc8785-v1:")
        assert res_ok.error_code is None
        assert res_ok.details is None

        # Failure case: duplicate key
        res_err = canonicalize_payload(b'{"k": 1, "k": 2}')
        assert res_err.is_ok is False
        assert res_err.canonical_bytes is None
        assert res_err.fingerprint is None
        assert res_err.error_code == "DUPLICATE_OBJECT_KEY"
        assert res_err.details is not None
        assert "Duplicate object key" in res_err.details
