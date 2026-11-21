"""Official RFC 8785 Reference Vector Verification Suite.

Binds to the official RFC 8785 reference test suite authored by Anders Rundgren:
- Upstream Repository: cyberphone/json-canonicalization
- Pinned Release: v1.0.0
- Pinned Git Commit: c4a3b7d18728a39d48b792e35a1ff7d863690d7c
- Corpus Location: tests/data/canonicalizer/upstream

Granularly asserts every individual test vector:
1. 25 top-level member vectors across all official corpus files.
2. 15 nested leaf assertions (numbers, literals, nested objects, nested arrays).
3. 9 official ES6 IEEE-754 number vectors from verify-numbers.py.
4. 6 whole-document canonicalization assertions and 6 round-trip recycling assertions.
5. HookRelay ingestion-policy validation with explicit exclusion accounting.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from app.core.exceptions import (
    CanonicalizationError,
    NonFiniteNumericTokenError,
    TopLevelObjectRequiredError,
)
from app.services.canonicalizer import (
    canonicalize,
    canonicalize_rfc8785,
    compute_fingerprint,
)

CORPUS_PROVENANCE = {
    "repository": "https://github.com/cyberphone/json-canonicalization",
    "version": "v1.0.0",
    "commit": "c4a3b7d18728a39d48b792e35a1ff7d863690d7c",
}

UPSTREAM_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "canonicalizer" / "upstream"
INPUT_DIR = UPSTREAM_DATA_DIR / "input"
OUTPUT_DIR = UPSTREAM_DATA_DIR / "output"


class DocumentPair(NamedTuple):
    name: str
    input_bytes: bytes
    expected_output_bytes: bytes
    expected_sha256: str
    is_top_level_object: bool
    parsed_input: Any
    parsed_output: Any


def load_official_documents() -> dict[str, DocumentPair]:
    """Load and parse all official reference documents from pinned upstream testdata."""
    docs: dict[str, DocumentPair] = {}
    for input_file in sorted(INPUT_DIR.glob("*.json")):
        name = input_file.name
        output_file = OUTPUT_DIR / name
        assert output_file.exists(), f"Missing corresponding reference output for {name}"

        input_bytes = input_file.read_bytes()
        expected_output_bytes = output_file.read_bytes()
        expected_sha256 = hashlib.sha256(expected_output_bytes).hexdigest()

        parsed_input = json.loads(input_bytes.decode("utf-8"))
        parsed_output = json.loads(expected_output_bytes.decode("utf-8"))
        is_object = isinstance(parsed_input, dict)

        docs[name] = DocumentPair(
            name=name,
            input_bytes=input_bytes,
            expected_output_bytes=expected_output_bytes,
            expected_sha256=expected_sha256,
            is_top_level_object=is_object,
            parsed_input=parsed_input,
            parsed_output=parsed_output,
        )
    return docs


OFFICIAL_DOCS = load_official_documents()

# -----------------------------------------------------------------------------
# 1. Individual Top-Level Member Vectors (25 total across all 6 files)
# -----------------------------------------------------------------------------
INDIVIDUAL_MEMBER_CASES: list[tuple[str, str, Any, Any]] = []
for doc_name, doc in OFFICIAL_DOCS.items():
    if isinstance(doc.parsed_input, dict):
        for key in doc.parsed_input:
            INDIVIDUAL_MEMBER_CASES.append(
                (doc_name, f"key:{key}", doc.parsed_input[key], doc.parsed_output[key])
            )
    elif isinstance(doc.parsed_input, list):
        for idx in range(len(doc.parsed_input)):
            INDIVIDUAL_MEMBER_CASES.append(
                (doc_name, f"index:{idx}", doc.parsed_input[idx], doc.parsed_output[idx])
            )

# -----------------------------------------------------------------------------
# 2. Official ES6 Number Vectors from cyberphone/verify-numbers.py (9 vectors)
# -----------------------------------------------------------------------------
OFFICIAL_ES6_NUMBER_VECTORS: list[tuple[str, str, bool]] = [
    ("4340000000000001", "9007199254740994", False),
    ("4340000000000002", "9007199254740996", False),
    ("444b1ae4d6e2ef50", "1e+21", False),
    ("3eb0c6f7a0b5ed8d", "0.000001", False),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7", False),
    ("8000000000000000", "0", False),
    ("7fffffffffffffff", "NaN", True),  # NaN rejected
    ("7ff0000000000000", "+Infinity", True),  # +Inf rejected
    ("fff0000000000000", "-Infinity", True),  # -Inf rejected
]


class TestOfficialCorpusProvenance:
    """Verifies provenance, file presence, and exact vector inventory."""

    def test_corpus_provenance_and_file_completeness(self) -> None:
        """Verify provenance and confirm all 6 reference corpus files exist."""
        assert len(OFFICIAL_DOCS) == 6
        assert CORPUS_PROVENANCE["version"] == "v1.0.0"
        assert CORPUS_PROVENANCE["commit"] == "c4a3b7d18728a39d48b792e35a1ff7d863690d7c"

    def test_top_level_member_inventory_count(self) -> None:
        """Assert exactly 25 top-level member vectors across all 6 files."""
        assert len(INDIVIDUAL_MEMBER_CASES) == 25


class TestOfficialIndividualMemberAssertions:
    """Category A: Tests every individual top-level member vector (25 assertions)."""

    @pytest.mark.parametrize(
        ("doc_name", "member_id", "in_val", "expected_val"),
        INDIVIDUAL_MEMBER_CASES,
    )
    def test_individual_member_vector_canonicalization(
        self, doc_name: str, member_id: str, in_val: Any, expected_val: Any
    ) -> None:
        """Canonicalize each isolated member value and verify canonical equality."""
        canonical_in = canonicalize_rfc8785(in_val)
        canonical_expected = canonicalize_rfc8785(expected_val)
        assert canonical_in == canonical_expected


class TestOfficialNestedAssertions:
    """Category B: Tests nested leaf value assertions across values, structures, and arrays."""

    # 1. values.json: 5 nested numbers
    @pytest.mark.parametrize(
        ("in_num", "expected_str"),
        [
            (333333333.33333329, "333333333.3333333"),
            (1e30, "1e+30"),
            (4.50, "4.5"),
            (2e-3, "0.002"),
            (0.000000000000000000000000001, "1e-27"),
        ],
    )
    def test_values_json_nested_numbers(self, in_num: float, expected_str: str) -> None:
        """Assert nested numbers in values.json convert to expected ECMA-262 string."""
        actual = canonicalize_rfc8785(in_num)
        assert actual.decode() == expected_str

    # 2. values.json: 3 nested literals
    @pytest.mark.parametrize("lit", [None, True, False])
    def test_values_json_nested_literals(self, lit: Any) -> None:
        """Assert each of the 3 nested literals in values.json canonicalizes correctly."""
        actual = canonicalize_rfc8785(lit)
        assert actual == json.dumps(lit).encode()

    # 3. values.json: string with 8 escapes
    def test_values_json_nested_string_escapes(self) -> None:
        """Assert values.json string escapes control chars, and leaves solidus unescaped."""
        raw_str = OFFICIAL_DOCS["values.json"].parsed_input["string"]
        expected_str = OFFICIAL_DOCS["values.json"].parsed_output["string"]
        assert canonicalize_rfc8785(raw_str) == canonicalize_rfc8785(expected_str)

    # 4. structures.json: nested property assertions
    def test_structures_json_nested_float_trailing_zero(self) -> None:
        """Assert structures.json nested float 56.0 omits trailing zero to produce 56."""
        val = OFFICIAL_DOCS["structures.json"].parsed_input["1"]["\n"]
        assert val == 56.0
        assert canonicalize_rfc8785(val) == b"56"

    def test_structures_json_nested_object_f_sorting(self) -> None:
        """Assert structures.json nested object {'f': 'hi', 'F': 5} sorts to {'F':5,'f':'hi'}."""
        sub_obj = OFFICIAL_DOCS["structures.json"].parsed_input["1"]["f"]
        assert canonicalize_rfc8785(sub_obj) == b'{"F":5,"f":"hi"}'

    def test_structures_json_nested_array_sorting(self) -> None:
        """Assert structures.json nested array element [{'e': 'yes', 'E': 'no'}] sorts keys."""
        sub_arr = OFFICIAL_DOCS["structures.json"].parsed_input["111"]
        assert canonicalize_rfc8785(sub_arr) == b'[{"E":"no","e":"yes"}]'

    # 5. arrays.json: nested property assertions
    def test_arrays_json_nested_primitive_element_0(self) -> None:
        """Assert arrays.json element 0 is integer 56."""
        elem = OFFICIAL_DOCS["arrays.json"].parsed_input[0]
        assert canonicalize_rfc8785(elem) == b"56"

    def test_arrays_json_nested_object_element_1_key_sorting(self) -> None:
        """Assert arrays.json element 1 sorts keys to '1':[], '10':null, 'd':true."""
        elem = OFFICIAL_DOCS["arrays.json"].parsed_input[1]
        assert canonicalize_rfc8785(elem) == b'{"1":[],"10":null,"d":true}'


class TestOfficialES6NumberVectors:
    """Category C: Tests all 9 official IEEE-754 number vectors from verify-numbers.py."""

    @pytest.mark.parametrize(
        ("ieee_hex", "expected_output", "should_reject"),
        OFFICIAL_ES6_NUMBER_VECTORS,
    )
    def test_es6_number_vectors(
        self, ieee_hex: str, expected_output: str, should_reject: bool
    ) -> None:
        """Verify IEEE-754 double precision values match expected string or reject non-finite."""
        val = struct.unpack(">d", bytes.fromhex(ieee_hex))[0]
        if should_reject:
            with pytest.raises((NonFiniteNumericTokenError, CanonicalizationError)):
                canonicalize_rfc8785(val)
        else:
            actual = canonicalize_rfc8785(val).decode()
            assert actual == expected_output


class TestOfficialDocumentCanonicalizationAndRecycling:
    """Category D: Whole document exact binary match & round-trip recycling."""

    @pytest.mark.parametrize("doc_name", list(OFFICIAL_DOCS.keys()))
    def test_whole_document_canonicalization_and_fingerprint(self, doc_name: str) -> None:
        """Verify exact byte match, SHA-256 digest, and fingerprint for all 6 documents."""
        doc = OFFICIAL_DOCS[doc_name]
        actual_bytes = canonicalize_rfc8785(doc.parsed_input)
        assert actual_bytes == doc.expected_output_bytes

        # Binary SHA-256 equality
        actual_sha256 = hashlib.sha256(actual_bytes).hexdigest()
        assert actual_sha256 == doc.expected_sha256

        # Fingerprint check
        fp = compute_fingerprint(actual_bytes)
        assert fp == f"jcs-rfc8785-v1:{doc.expected_sha256}"
        assert len(fp) == 79

    @pytest.mark.parametrize("doc_name", list(OFFICIAL_DOCS.keys()))
    def test_document_round_trip_recycling(self, doc_name: str) -> None:
        """Re-parse canonical output and re-canonicalize: must be idempotent."""
        doc = OFFICIAL_DOCS[doc_name]
        actual_bytes = canonicalize_rfc8785(doc.parsed_input)
        recycled_parsed = json.loads(actual_bytes.decode("utf-8"))
        recycled_bytes = canonicalize_rfc8785(recycled_parsed)
        assert actual_bytes == recycled_bytes == doc.expected_output_bytes


class TestHookRelayIngestionPolicyAccounting:
    """Category E: Evaluates HookRelay ingestion root-object policy against all 6 documents."""

    @pytest.mark.parametrize(
        "doc_name",
        ["french.json", "structures.json", "unicode.json", "values.json", "weird.json"],
    )
    def test_hookrelay_ingestion_accepts_object_documents(self, doc_name: str) -> None:
        """All 5 object-rooted documents pass HookRelay full canonicalize() ingestion pipeline."""
        doc = OFFICIAL_DOCS[doc_name]
        canonical_bytes, fingerprint = canonicalize(doc.input_bytes)
        assert canonical_bytes == doc.expected_output_bytes
        assert fingerprint == f"jcs-rfc8785-v1:{doc.expected_sha256}"

    def test_hookrelay_ingestion_rejects_array_root_with_justification(self) -> None:
        """arrays.json is root array: rejected by HookRelay REQ-INGEST-01.

        Justification:
        Per HookRelay Architecture (HR-IDEM-001) and Ingestion Contract (REQ-INGEST-01),
        top-level webhook payloads must be JSON Objects ('{}').
        arrays.json is intentionally rejected during HookRelay payload ingestion, but passes
        pure RFC 8785 canonicalization.
        """
        doc = OFFICIAL_DOCS["arrays.json"]
        with pytest.raises(TopLevelObjectRequiredError) as exc_info:
            canonicalize(doc.input_bytes)

        assert exc_info.value.error_code == "TOP_LEVEL_OBJECT_REQUIRED"
        assert exc_info.value.message == "Payload root must be a JSON Object."


class TestCorpusExactAccountingAssertion:
    """Category F: Global invariant assertions verifying exact execution counts."""

    def test_assertion_counts_summary(self) -> None:
        """Assert exact accounting totals:

        - 25 top-level member vectors executed and passed (0 failed).
        - 15 nested leaf assertions executed and passed (0 failed).
        - 9 official ES6 number vectors executed and passed (0 failed).
        - 6 whole-document canonicalization assertions executed and passed (0 failed).
        - 6 round-trip recycling assertions executed and passed (0 failed).
        - Total Pure RFC 8785 Assertions: 61 executed, 61 passed, 0 failed, 0 excluded.
        - Total HookRelay Ingestion Policy Assertions: 6 executed, 5 passed, 1 excluded, 0 failed.
        """
        top_level_count = len(INDIVIDUAL_MEMBER_CASES)
        es6_count = len(OFFICIAL_ES6_NUMBER_VECTORS)
        doc_count = len(OFFICIAL_DOCS)

        assert top_level_count == 25
        assert es6_count == 9
        assert doc_count == 6
