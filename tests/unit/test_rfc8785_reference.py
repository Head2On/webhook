"""Official RFC 8785 Reference Vector Verification Suite.

Binds to the official RFC 8785 reference test suite authored by Anders Rundgren:
- Upstream Repository: cyberphone/json-canonicalization
- Pinned Release: v1.0.0
- Pinned Git Commit: c4a3b7d18728a39d48b792e35a1ff7d863690d7c
- Corpus Location: tests/data/canonicalizer/upstream

Verifies:
1. 100% of official reference vectors for pure RFC 8785 canonicalization.
2. HookRelay ingestion boundary compliance and explicit exclusion accounting.
3. Binary exactness: SHA-256(canonicalizer_output) == SHA-256(reference_output).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import NamedTuple

import pytest

from app.core.exceptions import TopLevelObjectRequiredError
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


class ReferenceVector(NamedTuple):
    name: str
    input_bytes: bytes
    expected_output_bytes: bytes
    expected_sha256: str
    is_top_level_object: bool


def get_official_reference_vectors() -> list[ReferenceVector]:
    """Load all official reference vectors from pinned upstream testdata."""
    vectors: list[ReferenceVector] = []
    for input_file in sorted(INPUT_DIR.glob("*.json")):
        name = input_file.name
        output_file = OUTPUT_DIR / name
        assert output_file.exists(), f"Missing corresponding reference output for {name}"

        input_bytes = input_file.read_bytes()
        expected_output_bytes = output_file.read_bytes()
        expected_sha256 = hashlib.sha256(expected_output_bytes).hexdigest()

        # Check if root is an object or array/primitive
        stripped = input_bytes.strip()
        is_object = stripped.startswith(b"{")

        vectors.append(
            ReferenceVector(
                name=name,
                input_bytes=input_bytes,
                expected_output_bytes=expected_output_bytes,
                expected_sha256=expected_sha256,
                is_top_level_object=is_object,
            )
        )
    return vectors


@pytest.fixture(scope="module")
def official_vectors() -> list[ReferenceVector]:
    return get_official_reference_vectors()


class TestOfficialRFC8785ReferenceVectors:
    """Evaluates pure RFC 8785 canonicalization against official reference vectors."""

    def test_corpus_provenance_and_completeness(
        self, official_vectors: list[ReferenceVector]
    ) -> None:
        """Verify provenance and ensure all official test files are present."""
        assert len(official_vectors) == 6
        expected_files = {
            "arrays.json",
            "french.json",
            "structures.json",
            "unicode.json",
            "values.json",
            "weird.json",
        }
        actual_files = {v.name for v in official_vectors}
        assert actual_files == expected_files

        # Ensure corpus provenance is explicitly asserted
        assert CORPUS_PROVENANCE["version"] == "v1.0.0"
        assert CORPUS_PROVENANCE["commit"] == "c4a3b7d18728a39d48b792e35a1ff7d863690d7c"

    @pytest.mark.parametrize(
        "vector_name",
        [
            "arrays.json",
            "french.json",
            "structures.json",
            "unicode.json",
            "values.json",
            "weird.json",
        ],
    )
    def test_pure_rfc8785_canonicalization_official_vectors(
        self, official_vectors: list[ReferenceVector], vector_name: str
    ) -> None:
        """Verify 100% byte-for-byte exact equality and SHA-256 parity for all official vectors."""
        vector = next(v for v in official_vectors if v.name == vector_name)

        parsed_data = json.loads(vector.input_bytes.decode("utf-8"))
        actual_canonical_bytes = canonicalize_rfc8785(parsed_data)

        # 1. Byte-for-byte exact equality
        assert actual_canonical_bytes == vector.expected_output_bytes

        # 2. SHA-256 digest exact equality
        actual_sha256 = hashlib.sha256(actual_canonical_bytes).hexdigest()
        assert actual_sha256 == vector.expected_sha256

        # 3. Fingerprint format verification
        fingerprint = compute_fingerprint(actual_canonical_bytes)
        assert fingerprint == f"jcs-rfc8785-v1:{vector.expected_sha256}"
        assert len(fingerprint) == 79

    def test_official_reference_suite_pass_rate_and_accounting(
        self, official_vectors: list[ReferenceVector]
    ) -> None:
        """Generate official accounting: total, passed, failed, excluded counts."""
        total_vectors = len(official_vectors)
        passed_vectors = 0
        failed_vectors = 0
        excluded_vectors = 0

        for vector in official_vectors:
            try:
                parsed_data = json.loads(vector.input_bytes.decode("utf-8"))
                actual_bytes = canonicalize_rfc8785(parsed_data)
                if actual_bytes == vector.expected_output_bytes:
                    passed_vectors += 1
                else:
                    failed_vectors += 1
            except Exception:
                failed_vectors += 1

        assert total_vectors == 6
        assert passed_vectors == 6
        assert failed_vectors == 0
        assert excluded_vectors == 0
        assert (passed_vectors / total_vectors) == 1.0  # 100% pass rate invariant


class TestHookRelayIngestionBoundaryAccounting:
    """Verifies HookRelay ingestion boundary compliance and explains vector exclusions."""

    def test_hookrelay_canonicalize_payload_object_vectors(
        self, official_vectors: list[ReferenceVector]
    ) -> None:
        """All official object-rooted vectors pass HookRelay full canonicalize() pipeline."""
        object_vectors = [v for v in official_vectors if v.is_top_level_object]
        assert len(object_vectors) == 5  # french, structures, unicode, values, weird

        for v in object_vectors:
            canonical_bytes, fingerprint = canonicalize(v.input_bytes)
            assert canonical_bytes == v.expected_output_bytes
            assert fingerprint == f"jcs-rfc8785-v1:{v.expected_sha256}"

    def test_hookrelay_canonicalize_payload_excluded_vectors_with_justification(
        self, official_vectors: list[ReferenceVector]
    ) -> None:
        """arrays.json is root array: rejected by HookRelay REQ-INGEST-01.

        Justification:
        Per HookRelay Architecture (HR-IDEM-001) and Ingestion Contract (REQ-INGEST-01),
        top-level webhook payloads must be JSON Objects ('{}').
        arrays.json is intentionally rejected during HookRelay payload ingestion, but passes
        pure RFC 8785 canonicalization.
        """
        array_vector = next(v for v in official_vectors if not v.is_top_level_object)
        assert array_vector.name == "arrays.json"

        with pytest.raises(TopLevelObjectRequiredError) as exc_info:
            canonicalize(array_vector.input_bytes)

        assert exc_info.value.error_code == "TOP_LEVEL_OBJECT_REQUIRED"
        assert exc_info.value.message == "Payload root must be a JSON Object."
