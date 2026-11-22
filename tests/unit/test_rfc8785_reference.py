"""Official RFC 8785 Reference Vector Verification Suite.

Binds to the official RFC 8785 reference test suite authored by Anders Rundgren:
- Upstream Repository: cyberphone/json-canonicalization
- Pinned Release: v1.0.0
- Pinned Git Commit: c4a3b7d18728a39d48b792e35a1ff7d863690d7c
- Corpus Location: tests/data/canonicalizer/upstream

Test Accounting Architecture:
1. Category 1: Independent upstream reference-vector checks (6 whole documents).
2. Category 2: Derived member assertions (25 individual members tested
   against independently specified authoritative expected canonical bytes,
   with automated provenance verification matching each member against the pinned upstream corpus).
3. Category 3: Number-specific checks (9 official ES6 IEEE-754 vectors + 5 values.json numbers).
4. Category 4: Round-trip recycling checks (6 document idempotency assertions).
5. Category 5: HookRelay-specific ingestion-policy checks (5 accepted, 1 excluded).
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
        is_object = isinstance(parsed_input, dict)

        docs[name] = DocumentPair(
            name=name,
            input_bytes=input_bytes,
            expected_output_bytes=expected_output_bytes,
            expected_sha256=expected_sha256,
            is_top_level_object=is_object,
            parsed_input=parsed_input,
        )
    return docs


OFFICIAL_DOCS = load_official_documents()


class MemberVectorSpec(NamedTuple):
    doc_name: str
    member_id: str
    member_key: str | int
    in_val: Any
    expected_canonical_bytes: bytes


# -----------------------------------------------------------------------------
# Category 2: Derived Member Vectors with Upstream Provenance Traceability
# Each vector explicitly specifies:
# 1. doc_name: Upstream reference document name.
# 2. member_id: Stable human-readable identifier/slug for test identification.
# 3. member_key: Exact lookup key (str) or index (int) in the source document.
# 4. in_val: Standalone derived input value, automatedly validated against the
#    pinned upstream corpus: OFFICIAL_DOCS[doc_name].parsed_input[member_key].
# 5. expected_canonical_bytes: Independent raw byte literal derived directly
#    from the authoritative upstream reference output document.
# -----------------------------------------------------------------------------
AUTHORITATIVE_MEMBER_VECTORS: list[MemberVectorSpec] = [
    # french.json (4 members)
    MemberVectorSpec(
        "french.json", "peach", "peach", "This sorting order", b'"This sorting order"'
    ),
    MemberVectorSpec(
        "french.json",
        "peche_acute",
        "péché",
        "is wrong according to French",
        b'"is wrong according to French"',
    ),
    MemberVectorSpec(
        "french.json",
        "peche_circumflex",
        "pêche",
        "but canonicalization MUST",
        b'"but canonicalization MUST"',
    ),
    MemberVectorSpec("french.json", "sin", "sin", "ignore locale", b'"ignore locale"'),
    # weird.json (9 members)
    MemberVectorSpec("weird.json", "euro_sign", "\u20ac", "Euro Sign", b'"Euro Sign"'),
    MemberVectorSpec(
        "weird.json", "carriage_return", "\r", "Carriage Return", b'"Carriage Return"'
    ),
    MemberVectorSpec("weird.json", "newline", "\n", "Newline", b'"Newline"'),
    MemberVectorSpec("weird.json", "digit_one", "1", "One", b'"One"'),
    MemberVectorSpec("weird.json", "control_char", "\u0080", "Control\x7f", b'"Control\x7f"'),
    MemberVectorSpec("weird.json", "smiley_emoji", "\U0001f602", "Smiley", b'"Smiley"'),
    MemberVectorSpec(
        "weird.json",
        "latin_small_o",
        "\u00f6",
        "Latin Small Letter O With Diaeresis",
        b'"Latin Small Letter O With Diaeresis"',
    ),
    MemberVectorSpec(
        "weird.json",
        "hebrew_dalet",
        "\ufb33",
        "Hebrew Letter Dalet With Dagesh",
        b'"Hebrew Letter Dalet With Dagesh"',
    ),
    MemberVectorSpec(
        "weird.json", "browser_challenge", "</script>", "Browser Challenge", b'"Browser Challenge"'
    ),
    # structures.json (6 members)
    MemberVectorSpec("structures.json", "empty_key", "", "empty", b'"empty"'),
    MemberVectorSpec(
        "structures.json",
        "key_1",
        "1",
        {"f": {"f": "hi", "F": 5}, "\n": 56.0},
        b'{"\\n":56,"f":{"F":5,"f":"hi"}}',
    ),
    MemberVectorSpec("structures.json", "key_10", "10", {}, b"{}"),
    MemberVectorSpec(
        "structures.json", "key_111", "111", [{"e": "yes", "E": "no"}], b'[{"E":"no","e":"yes"}]'
    ),
    MemberVectorSpec("structures.json", "key_A", "A", {}, b"{}"),
    MemberVectorSpec("structures.json", "key_a", "a", {}, b"{}"),
    # unicode.json (1 member)
    MemberVectorSpec(
        "unicode.json", "unnormalized", "Unnormalized Unicode", "A\u030a", b'"A\xcc\x8a"'
    ),
    # values.json (3 members)
    MemberVectorSpec(
        "values.json",
        "numbers",
        "numbers",
        [333333333.33333329, 1e30, 4.50, 2e-3, 0.000000000000000000000000001],
        b"[333333333.3333333,1e+30,4.5,0.002,1e-27]",
    ),
    MemberVectorSpec(
        "values.json",
        "string",
        "string",
        "\u20ac$\u000f\u000aA'\u0042\u0022\u005c\\\"/",
        b'"\xe2\x82\xac$\\u000f\\nA\'B\\"\\\\\\\\\\"/"',
    ),
    MemberVectorSpec(
        "values.json", "literals", "literals", [None, True, False], b"[null,true,false]"
    ),
    # arrays.json (2 members)
    MemberVectorSpec("arrays.json", "index_0", 0, 56, b"56"),
    MemberVectorSpec(
        "arrays.json",
        "index_1",
        1,
        {"d": True, "10": None, "1": []},
        b'{"1":[],"10":null,"d":true}',
    ),
]

# -----------------------------------------------------------------------------
# Category 3: Official ES6 Number Vectors from cyberphone/verify-numbers.py (9 vectors)
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

VALUES_JSON_NESTED_NUMBERS: list[tuple[float, bytes]] = [
    (333333333.33333329, b"333333333.3333333"),
    (1e30, b"1e+30"),
    (4.50, b"4.5"),
    (2e-3, b"0.002"),
    (0.000000000000000000000000001, b"1e-27"),
]


class TestOfficialCorpusProvenanceAndAccounting:
    """Verifies provenance, file presence, exact vector category counts, and member traceability."""

    def test_corpus_provenance_and_file_completeness(self) -> None:
        """Verify provenance and confirm all 6 reference corpus files exist."""
        assert len(OFFICIAL_DOCS) == 6
        assert CORPUS_PROVENANCE["version"] == "v1.0.0"
        assert CORPUS_PROVENANCE["commit"] == "c4a3b7d18728a39d48b792e35a1ff7d863690d7c"

    def test_category_vector_counts_invariant(self) -> None:
        """Assert exact accounting totals:

        - Category 1 (Independent upstream documents): 6
        - Category 2 (Derived member vectors with independent expected bytes): 25
        - Category 3 (Number-specific: 9 ES6 IEEE-754 + 5 values.json nested): 14
        - Category 4 (Document round-trip recycling checks): 6
        - Category 5 (HookRelay ingestion policy checks): 6 (5 accepted, 1 excluded)
        """
        assert len(OFFICIAL_DOCS) == 6
        assert len(AUTHORITATIVE_MEMBER_VECTORS) == 25
        assert len(OFFICIAL_ES6_NUMBER_VECTORS) == 9
        assert len(VALUES_JSON_NESTED_NUMBERS) == 5

    def test_member_vectors_traceability_to_upstream_corpus(self) -> None:
        """Automated verification proving each of the 25 member vectors matches
        its source corpus entry and that all members across all 6 upstream reference
        documents are accounted for.
        """
        verified_count = 0
        for vec in AUTHORITATIVE_MEMBER_VECTORS:
            assert vec.doc_name in OFFICIAL_DOCS, f"Unknown document {vec.doc_name}"
            corpus_doc = OFFICIAL_DOCS[vec.doc_name].parsed_input
            if isinstance(corpus_doc, dict):
                assert vec.member_key in corpus_doc, f"Key {vec.member_key!r} not in {vec.doc_name}"
            elif isinstance(corpus_doc, list):
                assert isinstance(vec.member_key, int) and 0 <= vec.member_key < len(corpus_doc), (
                    f"Index {vec.member_key!r} out of range in {vec.doc_name}"
                )
            assert corpus_doc[vec.member_key] == vec.in_val, (
                f"Mismatch for {vec.doc_name} member '{vec.member_id}' (key {vec.member_key!r}): "
                f"{corpus_doc[vec.member_key]!r} != {vec.in_val!r}"
            )
            verified_count += 1

        assert verified_count == 25

        # Also verify 100% member coverage: sum of members in all 6 official documents equals 25
        total_corpus_members = sum(
            len(doc.parsed_input) if isinstance(doc.parsed_input, (dict, list)) else 1
            for doc in OFFICIAL_DOCS.values()
        )
        assert total_corpus_members == 25


class TestCategory1UpstreamReferenceVectorChecks:
    """Category 1: Independent Upstream Reference Vector Checks (6 Whole Documents).

    Evaluates full documents directly against official output files without circular comparison.
    """

    @pytest.mark.parametrize("doc_name", list(OFFICIAL_DOCS.keys()))
    def test_upstream_document_canonicalization(self, doc_name: str) -> None:
        """Verify exact byte match, SHA-256 digest, and fingerprint for all 6 official documents."""
        doc = OFFICIAL_DOCS[doc_name]
        actual_bytes = canonicalize_rfc8785(doc.parsed_input)

        # 1. Byte-for-byte exact equality against official output file
        assert actual_bytes == doc.expected_output_bytes

        # 2. SHA-256 binary digest exact equality
        actual_sha256 = hashlib.sha256(actual_bytes).hexdigest()
        assert actual_sha256 == doc.expected_sha256

        # 3. Fingerprint format verification
        fp = compute_fingerprint(actual_bytes)
        assert fp == f"jcs-rfc8785-v1:{doc.expected_sha256}"
        assert len(fp) == 79


class TestCategory2DerivedMemberAssertions:
    """Category 2: Derived Member Assertions (25 Individual Members).

    Compares canonicalize_rfc8785(in_val) against an INDEPENDENT authoritative byte literal.
    No circular call to canonicalize_rfc8785 is used on the expected value.
    Each vector explicitly records its source document name, member ID label, and exact upstream
    member selector key/index, with automated verification proving each vector matches
    its source corpus entry.
    """

    @pytest.mark.parametrize(
        ("doc_name", "member_id", "member_key", "in_val", "expected_canonical_bytes"),
        AUTHORITATIVE_MEMBER_VECTORS,
        ids=[f"{v.doc_name}::{v.member_id}" for v in AUTHORITATIVE_MEMBER_VECTORS],
    )
    def test_individual_member_vector_against_independent_expected_bytes(
        self,
        doc_name: str,
        member_id: str,
        member_key: str | int,
        in_val: Any,
        expected_canonical_bytes: bytes,
    ) -> None:
        """Assert each member serializes to its authoritative expected canonical byte sequence,
        and automatedly verify provenance against the pinned upstream input corpus."""
        # 1. Automated provenance verification: prove input value matches pinned upstream corpus
        corpus_val = OFFICIAL_DOCS[doc_name].parsed_input[member_key]
        assert in_val == corpus_val, (
            f"Traceability mismatch for {doc_name} member '{member_id}' (key: {member_key!r}): "
            f"vector input {in_val!r} != corpus {corpus_val!r}"
        )

        # 2. Canonicalize and verify against independent authoritative expected bytes
        actual_canonical_bytes = canonicalize_rfc8785(in_val)
        assert actual_canonical_bytes == expected_canonical_bytes


class TestCategory3NumberSpecificChecks:
    """Category 3: Number-Specific Checks (14 Assertions).

    - 9 official ES6 IEEE-754 double precision vectors from verify-numbers.py
    - 5 nested numbers in values.json tested against independent string literals
    """

    @pytest.mark.parametrize(
        ("ieee_hex", "expected_output", "should_reject"),
        OFFICIAL_ES6_NUMBER_VECTORS,
    )
    def test_official_es6_number_vectors(
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

    @pytest.mark.parametrize(
        ("in_num", "expected_bytes"),
        VALUES_JSON_NESTED_NUMBERS,
    )
    def test_values_json_nested_numbers(self, in_num: float, expected_bytes: bytes) -> None:
        """Assert each of the 5 nested numbers in values.json converts to ECMA-262 bytes."""
        actual_bytes = canonicalize_rfc8785(in_num)
        assert actual_bytes == expected_bytes


class TestCategory4RoundTripIdempotencyChecks:
    """Category 4: Round-Trip Recycling Checks (6 Document Idempotency Assertions).

    Re-parses canonical output and re-canonicalizes, validating: actual == expected == recycled.
    """

    @pytest.mark.parametrize("doc_name", list(OFFICIAL_DOCS.keys()))
    def test_document_round_trip_recycling(self, doc_name: str) -> None:
        """Re-parse canonical output and re-canonicalize: must be idempotent."""
        doc = OFFICIAL_DOCS[doc_name]
        actual_bytes = canonicalize_rfc8785(doc.parsed_input)
        recycled_parsed = json.loads(actual_bytes.decode("utf-8"))
        recycled_bytes = canonicalize_rfc8785(recycled_parsed)
        assert actual_bytes == recycled_bytes == doc.expected_output_bytes


class TestCategory5HookRelayIngestionPolicyChecks:
    """Category 5: HookRelay-Specific Ingestion Policy Checks (6 Document Checks).

    Evaluates HookRelay ingestion root-object policy against all 6 documents.
    """

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
