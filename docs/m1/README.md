# HookRelay — Milestone 1 (M1) Gate 1 & Gate 2 Documentation
## Canonicalizer and Idempotency Contract Documentation Index

**Milestone:** M1 — Event Ingestion & Idempotency Engine  
**Gate:** 2 — Canonicalizer Implementation  
**Status:** IMPLEMENTATION COMPLETE — READY FOR ODIN TECHNICAL REVIEW  
**Implementation Scope:** Canonicalization engine, library evaluation, and verification suites only. (Database migrations, models, repositories, and Gate 3/4 remain strictly unauthorized).

---

### Index of Deliverables

1. **[Document 01: Canonicalization Technical Contract](file:///E:/Projects/personal/webhook/docs/m1/01_canonicalization_technical_contract.md)**
   - Strict architectural separation: Canonicalizer domain engine (`Accepted` vs `Rejected`) decoupled from HTTP transport mapping.
   - Mapping client input errors to **`HTTP 400 Bad Request`** per approved `HR-IDEM-002`.
   - Depth 32 accepted by canonicalizer; depth 33 rejected.
   - Strict RFC 8785 (JCS) normative rules, safe integers $[-2^{53}+1, 2^{53}-1]$, lone surrogates/UTF-8, ECMA-262 float formatting (`-0.0` $\to$ `0`, `1e-6` $\to$ `0.000001`, `1e-7` $\to$ `1e-7`), SHA-256 (`jcs-rfc8785-v1`).
   - Disciplined library evaluation criteria (evaluating maintained Python JCS packages against reference corpus before considering compiled/custom options).
   - PostgreSQL `BYTEA` storage documented as a proposed technical recommendation for Founder decision.

2. **[Document 02: Idempotency Transaction and Concurrency Contract](file:///E:/Projects/personal/webhook/docs/m1/02_idempotency_transaction_concurrency_contract.md)**
   - Authoritative HTTP status table: New key $\to$ **HTTP 202 Accepted**; Duplicate (matching fingerprint) $\to$ **HTTP 200 OK** (returning original event acceptance body); Mismatch $\to$ **HTTP 409 Conflict**; Malformed $\to$ **HTTP 400 Bad Request**.
   - **Strict Invariant: Never use HTTP 202 for a duplicate request.**
   - Expiry boundary: Active = `expires_at > statement_timestamp()`; Expired = `expires_at <= statement_timestamp()`.
   - Lock timeout: explicitly **`TBD — determined through Stage B capacity and load testing`** (no zero-wait language; 500ms and 2s noted as proposed Stage B benchmarks).
   - Concurrent expired-key replacement: 7-step sequence (`FOR UPDATE` $\to$ retire $\to$ insert replacement $\to$ partial unique index safeguard $\to$ rollback $\to$ fresh read $\to$ compare). Two competing requests never create duplicate Events.
   - Partial unique index `idx_idempotency_project_key_active` (`WHERE retired_at IS NULL`) and deferred foreign key `DEFERRABLE INITIALLY DEFERRED` per `HR-ARCH-001`.
   - Handling of `response_body IS NULL` and confirmation that incomplete records cannot become visible as committed acceptance.

3. **[Document 03: Canonicalization Rejection and Boundary Test Matrix](file:///E:/Projects/personal/webhook/docs/m1/03_canonicalization_test_matrix.md)**
   - Comprehensive test matrix for Gate 2 verification with exact status codes: HTTP 202 for new, HTTP 200 for duplicate, HTTP 409 for conflict, HTTP 400 for input errors (depth 33, unsafe integers, invalid Unicode, duplicate keys, non-object roots), HTTP 413 for size (proposed), HTTP 415 for content type (unresolved).
   - Specific boundary cases for nesting depth (32 accepted, 33 rejected), integer limits, Unicode errors, float formatting (`-0.0`, `1e-6`, `1e-7`), lock timeouts, and concurrent expired-key replacement tests (same-payload and different-payload cases).

4. **[Document 04: Reference Vector Verification Specification](file:///E:/Projects/personal/webhook/docs/m1/04_reference_vector_verification_specification.md)**
   - Binding to official `cyberphone/json-canonicalization` reference test corpus (`v1.0.0`, commit `c4a3b7d18728a39d48b792e35a1ff7d863690d7c`).
   - Strengthened Gate 2 exit criteria (100% reference pass rate, zero unexplained deviations, complete coverage demonstration, explicit justification for any exclusions).
   - Disciplined phased library evaluation protocol prioritizing maintained Python JCS libraries.

5. **[Document 05: Traceability Matrix and Architecture Decisions](file:///E:/Projects/personal/webhook/docs/m1/05_traceability_matrix.md)**
   - Traceability table mapping all requirements to `HR-ARCH-001`, `HR-IDEM-001`, `HR-IDEM-002`, and `HR-CANON-001`..`005`.
   - Clear distinction between approved architecture decisions and proposed technical recommendations (PostgreSQL `BYTEA` storage, `lock_timeout` TBD, transport mappings) preserving the Founder's decision authority.

6. **[Document 06: RFC 8785 Library Evaluation & Selection Report](file:///E:/Projects/personal/webhook/docs/m1/06_library_evaluation_report.md)**
   - Comparative evaluation between `rfc8785==0.1.4` and `jcs==0.3.0`.
   - Float serialization validation (`-0.0` $\to$ `0`, `1e-6` $\to$ `0.000001`, `1e-7` $\to$ `1e-7`).
   - Safe integer range boundary enforcement ($2^{53}-1$ pass vs $2^{53}$ fail).
   - Full 100% pass verification on official reference vectors.
   - Justification for selecting `rfc8785==0.1.4` (Trail of Bits).

---

### Invariant Confirmation
- **Documentation only.**
- **Zero Python implementation code written or modified.**
- **Zero database migrations or schema files created.**
- **Zero changes made to M0 files or existing application code.**
- **Zero changes to previously approved architecture decisions.**
- **Stopped for Odin technical review.**
