# HookRelay M1 Gate 1 — Technical Specification
# Document 04: Reference Vector Verification Specification

- **Document Version:** 1.3.0
- **Milestone:** M1 — Event Ingestion & Idempotency Engine
- **Gate:** 1 — Technical Contract & Architecture Specification
- **Status:** Complete — Revised per Anna Independent Review & Odin Final Requirements
- **Reference Corpus:** `cyberphone/json-canonicalization` (Official RFC 8785 Reference Suite)

---

## 1. Upstream Verification Authority

To ensure uncompromised interoperability and strict RFC 8785 compliance, HookRelay binds its canonicalization verification to the official reference test suite authored by the RFC 8785 editor (Anders Rundgren):

- **Repository:** `https://github.com/cyberphone/json-canonicalization`
- **Pinned Release / Tag:** `v1.0.0`
- **Pinned Git Commit Hash:** `c4a3b7d18728a39d48b792e35a1ff7d863690d7c`
- **Corpus Location within Repository:** `/testdata`

---

## 2. Gate 2 Exit Criteria & Verification Invariants (Mandatory Condition)

Gate 2 implementation approval requires passing automated test execution under strengthened exit criteria. **Gate 2 cannot pass unless all of the following conditions are met:**

1. **100% Reference Pass Rate:** 100% of the selected official `cyberphone/json-canonicalization` reference vectors must pass without exception.
2. **Zero Unexplained Deviations:** Any divergence from the reference byte output constitutes a blocking defect.
3. **Recorded Corpus Provenance:** The exact corpus version (`v1.0.0`) and Git commit (`c4a3b7d18728a39d48b792e35a1ff7d863690d7c`) must be recorded in the test output.
4. **Complete Coverage Demonstration:** Running the vectors is not enough; the verification harness must output a complete coverage report validating that all reference files were executed.
5. **Explicit Justification for Exclusions:** Any excluded or unsupported vector (e.g. non-object top-level primitives that HookRelay rejects by design) must be explicitly documented and justified rather than silently omitted.
6. **HookRelay-Specific Edge Case Coverage:** All known edge cases from `HR-IDEM-002` (nesting depth 32/33, safe integer range, Unicode surrogates, duplicate keys, concurrent expired-key replacement) must have dedicated passing automated tests.
7. **Binary Exactness:** Validation compares the SHA-256 digest of the canonicalizer output against the SHA-256 digest of the reference output file:
   $$\text{SHA-256}(\text{CanonicalizerOutput}) == \text{SHA-256}(\text{ReferenceOutputFile})$$

---

## 3. Official Test Vector Categories

The `cyberphone/json-canonicalization` test suite provides paired input (`input/*.json`) and expected output (`output/*.json`) files covering:

### 3.1. Structural Key Sorting (`key-sorting.json`)
- Evaluates recursive dictionary ordering.
- Verifies UCS-2 / UTF-16 code unit ordering vs. naive ASCII ordering.
- Tests sorting of numeric-string keys, mixed-case keys, and multi-byte Unicode keys.

### 3.2. String Escaping & Unicode Serialization (`string-escaping.json`)
- Verifies that solidus `/` remains unescaped.
- Verifies that quotation mark `\"` and reverse solidus `\\` are escaped.
- Verifies control character escape representations (`\u0000` through `\u001f`) with lowercase hexadecimal letters.
- Verifies unescaped serialization of non-ASCII Unicode code points as raw UTF-8.

### 3.3. ECMAScript Number Formatting (`number-formatting.json`)
- Evaluates integer representations, negative zero removal (`-0.0` -> `0`), and trailing zero elimination (`1.0` -> `1`).
- Tests scientific notation thresholds ($10^{-6}$ decimal vs. $10^{-7}$ exponential; $10^{20}$ decimal vs. $10^{21}$ exponential).
- Tests subnormal IEEE 754 64-bit float conversions.

---

## 4. Library Evaluation Criteria (Normative Gate 2 Strategy)

Per technical review instructions, HookRelay enforces a disciplined, evidence-based library selection process:

1. **Do Not Assume Compliance:** HookRelay will not assume an external library is compliant merely because it claims RFC 8785 support.
2. **Phase 1 Evaluation:** The primary evaluation step in Gate 2 will execute the official test suite against maintained, existing Python JCS implementations (such as `rfc8785` and `jcs`).
3. **Mandatory Floating-Point Verifications:** The candidate library must be verified empirically against the required float serialization behaviors:
   - `-0.0` $\to$ `0`
   - `1e-6` $\to$ `0.000001`
   - `1e-7` $\to$ `1e-7`
4. **Pass Criteria:** If a maintained package passes **100%** of the official reference suite and satisfies HookRelay's boundary validation hooks (nesting depth 32, safe integer range), it will be selected.
5. **Custom Serialization Restriction:** Custom serialization or compiled C/Rust extensions will **NOT** be introduced unless library evaluation demonstrates that maintained packages fail reference vectors, and any such proposal is explicitly documented and approved.

---

## 5. HookRelay-Specific Extended Test Suite

Because RFC 8785 specifies canonicalization for *general* JSON, it does not mandate HookRelay's strict ingestion constraints. Therefore, the Gate 2 test suite must incorporate a secondary test suite: `tests/unit/test_canonicalizer_extended.py`:

```text
tests/data/canonicalizer/
├── upstream/                     # Pinned cyberphone/json-canonicalization corpus (c4a3b7d)
│   ├── input/
│   └── output/
└── hookrelay_extended/           # HookRelay-specific boundary vectors
    ├── depth_limits/             # Depth 32 vs 33 tests
    ├── unsafe_integers/          # Integers outside [-(2^53-1), 2^53-1]
    ├── unicode_surrogates/       # Lone \uD800, \uDFFF, overlong UTF-8
    ├── framing_boundaries/       # 1 MiB boundary, top-level arrays, duplicate keys
    └── concurrency_scenarios/    # Concurrent expired-key replacement, lock timeouts, rollback
```

---

## 6. Automated Verification Harness Protocol

In Gate 2, the test harness must be implemented with pytest:

```python
# Specification of test execution structure (Gate 2 contract requirement)
# File: tests/integration/test_rfc8785_reference.py

def test_rfc8785_official_vectors(reference_vector_pair):
    """
    1. Read input JSON bytes from pinned testdata (commit c4a3b7d).
    2. Execute HookRelay canonicalizer candidate.
    3. Read expected reference output bytes.
    4. Assert byte-for-byte exact equality.
    5. Assert SHA-256 fingerprint exact equality.
    """
    ...

def test_hookrelay_rejection_matrix(boundary_test_case):
    """
    1. Read boundary test case.
    2. Pass to HookRelay ingestion lexer / canonicalizer.
    3. Assert expected HTTP exception, status code (HTTP 400), and error code.
    """
    ...
```
