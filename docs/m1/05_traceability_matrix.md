# HookRelay M1 Gate 1 — Technical Specification
# Document 05: Traceability Matrix and Architecture Decisions

- **Document Version:** 1.3.0
- **Milestone:** M1 — Event Ingestion & Idempotency Engine
- **Gate:** 1 — Technical Contract & Architecture Specification
- **Status:** Complete — Revised per Anna Independent Review & Odin Final Requirements
- **Governing Architecture Baseline:** `HR-ARCH-001`, `HR-IDEM-001`, `HR-IDEM-002`, `HR-CANON-001` through `HR-CANON-005`

---

## 1. HTTP Status-Code Source-of-Truth Table

Per Odin review and Anna's verification requirements, all HTTP response codes in HookRelay are traceable to their exact authority:

| HTTP Status | Meaning | Authority |
|---|---|---|
| **200 OK** | Existing key, identical payload fingerprint (returns original acceptance body) | **HR-IDEM-002** (Approved) |
| **202 Accepted** | New event accepted and queued for delivery | **HR-IDEM-002** (Approved) |
| **400 Bad Request** | Invalid JSON or canonicalization rejection (nesting depth > 32, unsafe integer, invalid Unicode, duplicate key, non-object root) | **HR-IDEM-002** (Approved) |
| **409 Conflict** | Existing active key reused with different payload fingerprint | **HR-IDEM-002** (Approved) |
| **413 Payload Too Large** | Payload exceeds 1 MiB streaming limit | Proposed transport mapping; pending explicit founder approval |
| **415 Unsupported Media Type** | Unsupported media type or unsupported compression | Unresolved authority question; pending explicit founder approval |

---

## 2. Requirement Traceability Matrix

This matrix maps every M1 Gate 1 requirement from `odin.md` to its governing architecture decision, specification section, expected behavior, and explicit acceptance criterion:

| Requirement ID | Requirement Description | Governing Decision | Contract Reference | Expected Behavior | Acceptance Criterion |
|---|---|:---:|:---:|---|---|
| **REQ-CANON-01** | RFC 8785 (JCS) Compliance | `HR-IDEM-001` | Doc 01, §3; Doc 04, §2 | Strict compliance with RFC 8785 JCS encoding rules. | 100% pass rate on official `cyberphone/json-canonicalization` vectors. Zero unexplained deviations. |
| **REQ-CANON-02** | SHA-256 Fingerprinting | `HR-IDEM-001` | Doc 01, §5.3 | Canonical bytes hashed with SHA-256; prefixed with `jcs-rfc8785-v1:`. | Output is 79-character string `jcs-rfc8785-v1:<64-hex-digits>`. |
| **REQ-CANON-03** | Raw Payload Storage | Proposed Recommendation | Doc 01, §2; Doc 02, §2.2 | Raw request payload stored separately and unchanged. PostgreSQL `BYTEA` proposed for v1 (payloads $\le 1\text{ MiB}$). | Proposed recommendation submitted for Founder decision; external object store out of scope. |
| **REQ-DEFECT-01** | Nesting Depth Enforcement | `HR-CANON-001`, `HR-IDEM-002` | Doc 01, §4.1; Doc 03, §2 | Max depth 32 is valid and accepted; depth 33 is rejected. | Depth 32 accepted by canonicalizer; depth 33 returns HTTP 400 `PAYLOAD_NESTING_DEPTH_EXCEEDED`. |
| **REQ-DEFECT-02** | Unsafe Integer Range | `HR-CANON-002`, `HR-IDEM-002` | Doc 01, §4.2; Doc 03, §2 | Enforce safe integer range $[-(2^{53}-1), +(2^{53}-1)]$. | Tokens with $\|n\| > 9007199254740991$ rejected with HTTP 400 `UNSAFE_INTEGER_RANGE_EXCEEDED`. |
| **REQ-DEFECT-03** | Unicode & Surrogate Validation | `HR-CANON-003`, `HR-IDEM-002` | Doc 01, §4.3; Doc 03, §2 | Reject lone surrogates (`\uD800`, `\uDFFF`) and invalid UTF-8 octets. | Reject invalid sequences with HTTP 400 `INVALID_UNICODE_SEQUENCE`. |
| **REQ-DEFECT-04** | ECMA-262 Numeric Serialization | `HR-CANON-004` | Doc 01, §4.4; Doc 04, §4 | Conforms to ECMA-262 `Number::toString()`. Prioritize maintained JCS evaluation. | `-0.0` serialized as `0`; `1e-6` as `0.000001`; `1e-7` as `1e-7`. |
| **REQ-DEFECT-05** | SQL Idempotency Concurrency | `HR-CANON-005` | Doc 02, §4; Doc 03, §2 | Traps `23505`, immediate rollback, fresh transaction re-read, lock timeout TBD. | Match $\to$ HTTP 200; Mismatch $\to$ HTTP 409; Never HTTP 202 on duplicate; Zero HTTP 500 under concurrency. |
| **REQ-INGEST-01** | Top-Level Object Only | `HR-IDEM-001`, `HR-IDEM-002` | Doc 01, §5.1; Doc 03, §2 | Root of JSON payload must be an Object `{}`. | Top-level array, string, number, or primitive returns HTTP 400 `TOP_LEVEL_OBJECT_REQUIRED`. |
| **REQ-INGEST-02** | Duplicate Key Detection | `HR-IDEM-001`, `HR-IDEM-002` | Doc 01, §5.2; Doc 03, §2 | Duplicate keys rejected after escape decoding. | `{"a": 1, "\u0061": 2}` rejected with HTTP 400 `DUPLICATE_OBJECT_KEY`. |
| **REQ-INGEST-03** | Streaming Size Limit (1 MiB) | Proposed Mapping | Doc 01, §2; Doc 03, §2 | 1,048,576 byte limit enforced during streaming. | Byte 1,048,577 terminates stream with HTTP 413 `PAYLOAD_TOO_LARGE`. Pending explicit Founder approval. |
| **REQ-INGEST-04** | Unsupported Compression | Unresolved Authority | Doc 01, §2; Doc 03, §2 | Compressed payloads rejected in M1. | Non-identity `Content-Encoding` returns HTTP 415 `UNSUPPORTED_MEDIA_TYPE`. Pending explicit Founder approval. |
| **REQ-IDEM-01** | Partial Unique Index | `HR-IDEM-002` | Doc 02, §2.1 | Partial index on `(project_id, idempotency_key)` `WHERE retired_at IS NULL`. | Enforces active uniqueness; allows expired/retired key reuse. |
| **REQ-IDEM-02** | Deferred Foreign Key | `HR-ARCH-001` | Doc 02, §2.1 | FK from `idempotency_keys` to `events` is `DEFERRABLE INITIALLY DEFERRED`. | Permits inserting idempotency claim before event creation in a single transaction. |
| **REQ-IDEM-03** | Response Status Contract | `HR-IDEM-002` | Doc 02, §1, §5 | Strict HTTP response mapping: New $\to$ 202; Duplicate $\to$ 200; Mismatch $\to$ 409. | Duplicate returns original event acceptance body. Never 202 for duplicate; Never 500 on conflict. |
| **REQ-IDEM-04** | Incomplete Record Protection | `HR-CANON-005` | Doc 02, §5 | Incomplete records (`response_body IS NULL`) cannot be visible as committed acceptance. | Atomic transaction writes response before commit; uncommitted rows roll back invisibly. |
| **REQ-IDEM-05** | Expiry Boundary Definition | Anna Review / Odin Final | Doc 02, §3.1 | Active: `expires_at > statement_timestamp()`; Expired: `expires_at <= statement_timestamp()`. | Key is never active at exact expiration timestamp. Consistent across all docs and SQL. |
| **REQ-IDEM-06** | Concurrent Expired-Key Replacement | Anna Review / Odin Final | Doc 02, §4.2; Doc 03, §2 | FOR UPDATE -> retire -> insert replacement claim -> partial unique index safeguard -> rollback -> fresh read -> compare. | Exactly one replacement Event created under concurrency. Both same-payload requests receive HTTP 200; different-payload receives HTTP 409. Zero duplicate Events. |
| **REQ-IDEM-07** | Lock Timeout Specification | Anna Review / Odin Final | Doc 02, §3.2 | Lock timeout is `TBD — determined through Stage B capacity and load testing`. | No zero-wait language; 500ms and 2s recorded as proposed testing benchmarks. |

---

## 3. Approved Decisions vs. Proposed Recommendations

### 3.1. Approved Governing Architecture Decisions
1. **`HR-IDEM-001` & `HR-IDEM-002`:**
   - RFC 8785 (JCS) canonicalization and SHA-256 fingerprinting (`jcs-rfc8785-v1`).
   - Ingestion payload errors map to **`HTTP 400 Bad Request`**.
   - Partial unique index `idx_idempotency_project_key_active` (`WHERE retired_at IS NULL`).
   - Response code contract: New event $\to$ `HTTP 202 Accepted`; Duplicate $\to$ `HTTP 200 OK` (returning original acceptance body); Mismatch $\to$ `HTTP 409 Conflict`.
   - Invariant: Never return HTTP 202 for a duplicate request; never return HTTP 500 on uniqueness conflicts.
   - Retention policy range: 1–60 days, default 7 days.
2. **`HR-ARCH-001`:**
   - Mutual foreign keys between `idempotency_keys` and `events` use `DEFERRABLE INITIALLY DEFERRED`.

### 3.2. Proposed Technical Recommendations (Awaiting Founder Decision)
The following items are formal technical recommendations submitted for the Founder's review and decision; they are deliberately **not** labeled as approved ADRs:

1. **Storage Approach:** Propose using PostgreSQL `BYTEA` in `events.raw_payload_bytes` for v1 payload storage (payloads up to 1 MiB). External object storage (S3/MinIO) remains outside the v1 scope.
2. **Lock Timeout:** Documented as `TBD — determined through Stage B capacity and load testing`. (500ms and 2s proposed as Stage B benchmarks).
3. **Transport Mappings:** HTTP 413 and HTTP 415 are recorded as proposed transport mappings pending explicit Founder sign-off.

---

## 4. Numeric Serialization Evaluation Protocol (Gate 2 Execution)

Per technical review instructions, Gate 2 will adhere to the following evaluation criteria:
- **Phase 1:** Test maintained Python JCS implementations (e.g. `rfc8785`, `jcs`) directly against Anders Rundgren's official `cyberphone/json-canonicalization` reference test corpus.
- **Phase 2:** Verify candidate libraries against mandatory float serialization examples:
  - `-0.0` $\to$ `0`
  - `1e-6` $\to$ `0.000001`
  - `1e-7` $\to$ `1e-7`
- **Phase 3:** If an existing maintained package passes **100% of official reference vectors** and satisfies HookRelay boundary constraints, it will be adopted.
- **Phase 4 (Contingency):** A compiled C/Rust extension (e.g. PyO3 binding) will only be considered if maintained Python implementations fail official reference vectors or exhibit unresolvable ECMA-262 numeric discrepancies.
