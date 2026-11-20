# HookRelay M1 Gate 1 — Technical Specification
# Document 03: Canonicalization Rejection and Boundary Test Matrix

- **Document Version:** 1.3.0
- **Milestone:** M1 — Event Ingestion & Idempotency Engine
- **Gate:** 1 — Technical Contract & Architecture Specification
- **Status:** Complete — Revised per Anna Independent Review & Odin Final Requirements
- **Scope:** HookRelay-Specific Canonicalization, Framing, and Idempotency Conformance Matrix

---

## 1. Overview & Authority Baseline

This matrix defines the normative acceptance criteria for Gate 2 verification. Every test vector listed herein must have an automated test in the Gate 2 test suite.

- **Target Pass Rate:** **100%** (zero failures, zero unexplained deviations).
- **Architecture Separation:**
  - **Canonicalizer Engine Result:** Evaluates pure domain transformation (`Accepted` vs `Rejected`).
  - **HTTP Ingestion Mapping:** Maps client input errors to **`HTTP 400 Bad Request`** per `HR-IDEM-002`.
- **Expiry Boundary:**
  - Active: `expires_at > statement_timestamp()`
  - Expired: `expires_at <= statement_timestamp()` (a key is never active at its exact expiration time).
- **HTTP Status Source of Truth:**
  - New Ingestion Request: **`HTTP 202 Accepted`** (`HR-IDEM-002`)
  - Duplicate Request (Identical Fingerprint): **`HTTP 200 OK`** (`HR-IDEM-002`)
  - Conflicting Request (Different Fingerprint): **`HTTP 409 Conflict`** (`HR-IDEM-002`)
  - Malformed Input / Rejection: **`HTTP 400 Bad Request`** (`HR-IDEM-002`)
  - Payload Exceeds 1 MiB: **`HTTP 413 Payload Too Large`** (Proposed transport mapping)
  - Unsupported Media/Compression: **`HTTP 415 Unsupported Media Type`** (Unresolved authority question)

---

## 2. Test Matrix by Defect and Functional Category

### Category 1: JSON Nesting Depth Limits (`HR-CANON-001`)

| Test ID | Description / Input Sample | Nesting Depth | Canonicalizer Result | Ingestion HTTP Status | Expected Error Code | Acceptance Criterion |
|---|---|:---:|:---:|:---:|---|---|
| **DEPTH-01** | Empty JSON object: `{}` | 1 | **Accepted** | `202` | None | Accepted as valid root container. |
| **DEPTH-02** | Single-level nested object: `{"a": {"b": 1}}` | 2 | **Accepted** | `202` | None | Accepted. |
| **DEPTH-03** | Max allowed object depth: `{"k1":{"k2":...{"k32":1}...}}` | 32 | **Accepted** | N/A (Domain) | None | Boundary pass: depth 32 is valid and accepted by the canonicalizer. |
| **DEPTH-04** | Off-by-one depth overflow: `{"k1":{"k2":...{"k32":{"k33":1}}...}}` | 33 | **Rejected** | `400` | `PAYLOAD_NESTING_DEPTH_EXCEEDED` | Boundary fail: depth 33 rejected during streaming lexing. Returns HTTP 400 per HR-IDEM-002. |
| **DEPTH-05** | Max allowed array depth: `{"a": [[[[... 31 nested arrays ...]]]]}` | 32 | **Accepted** | N/A (Domain) | None | Boundary pass: object (1) + 31 nested arrays = depth 32. Accepted by canonicalizer. |
| **DEPTH-06** | Array depth overflow: `{"a": [[[[... 32 nested arrays ...]]]]}` | 33 | **Rejected** | `400` | `PAYLOAD_NESTING_DEPTH_EXCEEDED` | Boundary fail: object (1) + 32 nested arrays = depth 33. Returns HTTP 400 per HR-IDEM-002. |
| **DEPTH-07** | Mixed alternating object/array nesting reaching depth 33 | 33 | **Rejected** | `400` | `PAYLOAD_NESTING_DEPTH_EXCEEDED` | Rejected at opening bracket/brace of depth 33. Returns HTTP 400 per HR-IDEM-002. |

---

### Category 2: Safe Integer Boundary Enforcement (`HR-CANON-002`)

| Test ID | Description / Input Token | Token Value | Canonicalizer Result | Ingestion HTTP Status | Expected Error Code | Acceptance Criterion |
|---|---|:---:|:---:|:---:|---|---|
| **INT-01** | Zero integer: `{"val": 0}` | 0 | **Accepted** | `202` | None | Accepted, canonicalized as `"val":0`. |
| **INT-02** | Max Safe Integer ($2^{53} - 1$): `{"val": 9007199254740991}` | $9007199254740991$ | **Accepted** | `202` | None | Boundary pass: serialized without precision loss. |
| **INT-03** | Min Safe Integer ($-(2^{53} - 1)$): `{"val": -9007199254740991}` | $-9007199254740991$ | **Accepted** | `202` | None | Boundary pass: serialized without precision loss. |
| **INT-04** | Positive unsafe boundary ($2^{53}$): `{"val": 9007199254740992}` | $9007199254740992$ | **Rejected** | `400` | `UNSAFE_INTEGER_RANGE_EXCEEDED` | Strict rejection during token scan. Returns HTTP 400. |
| **INT-05** | Negative unsafe boundary ($-2^{53}$): `{"val": -9007199254740992}` | $-9007199254740992$ | **Rejected** | `400` | `UNSAFE_INTEGER_RANGE_EXCEEDED` | Strict rejection during token scan. Returns HTTP 400. |
| **INT-06** | 64-bit integer overflow: `{"val": 9223372036854775807}` | $2^{63} - 1$ | **Rejected** | `400` | `UNSAFE_INTEGER_RANGE_EXCEEDED` | Rejected without silent truncation. Returns HTTP 400. |
| **INT-07** | Unbounded large integer string: `{"val": 1000000000000000000000000000000}` | $10^{30}$ | **Rejected** | `400` | `UNSAFE_INTEGER_RANGE_EXCEEDED` | Rejected during token scan. Returns HTTP 400. |

---

### Category 3: Unicode & Surrogate Validation (`HR-CANON-003`)

| Test ID | Description / Byte Sequence | Input String Literal | Canonicalizer Result | Ingestion HTTP Status | Expected Error Code | Acceptance Criterion |
|---|---|---|:---:|:---:|---|---|
| **UNI-01** | Valid UTF-8 ASCII | `{"key": "HookRelay"}` | **Accepted** | `202` | None | Accepted. |
| **UNI-02** | Valid multi-byte UTF-8 (Greek, Cyrillic, CJK, Emoji) | `{"msg": "Hello \u4e16\u754c \ud83d\ude80"}` | **Accepted** | `202` | None | Surrogates paired into valid emoji 🚀, output as raw UTF-8. |
| **UNI-03** | Lone high surrogate | `{"msg": "\uD800"}` | **Rejected** | `400` | `INVALID_UNICODE_SEQUENCE` | Rejected: high surrogate without low surrogate. Returns HTTP 400. |
| **UNI-04** | Lone low surrogate | `{"msg": "\uDFFF"}` | **Rejected** | `400` | `INVALID_UNICODE_SEQUENCE` | Rejected: low surrogate without high surrogate. Returns HTTP 400. |
| **UNI-05** | Inverted surrogate pair order | `{"msg": "\uDC00\uD800"}` | **Rejected** | `400` | `INVALID_UNICODE_SEQUENCE` | Low surrogate followed by high surrogate rejected. Returns HTTP 400. |
| **UNI-06** | Invalid overlong UTF-8 byte sequence (`0xC0 0xAF`) | Raw octets `0xC0 0xAF` | **Rejected** | `400` | `INVALID_UNICODE_SEQUENCE` | Fails UTF-8 decoder immediately. Returns HTTP 400. |
| **UNI-07** | Orphan UTF-8 continuation byte (`0x80`) | Raw octet `0x80` outside multi-byte | **Rejected** | `400` | `INVALID_UNICODE_SEQUENCE` | Fails UTF-8 decoder immediately. Returns HTTP 400. |
| **UNI-08** | Truncated multi-byte sequence (`0xF0 0x90 0x80`) | Missing 4th byte of 4-byte char | **Rejected** | `400` | `INVALID_UNICODE_SEQUENCE` | Fails UTF-8 decoder immediately. Returns HTTP 400. |

---

### Category 4: Numeric Serialization & ECMA-262 Conformance (`HR-CANON-004`)

| Test ID | Description / Input Number | Input Token | Expected Canonical Serialized String | Acceptance Criterion |
|---|---|:---:|:---:|---|
| **NUM-01** | Negative zero (Mandatory Condition) | `-0.0` | `0` | Sign stripped; serialized as integer zero per ECMA-262 7.1.12.1. |
| **NUM-02** | Small decimal exponent transition (Mandatory Condition) | `0.000001` (`1e-6`) | `0.000001` | Non-exponential decimal notation used for values $\ge 10^{-6}$. |
| **NUM-03** | Small exponential transition (Mandatory Condition) | `0.0000001` (`1e-7`) | `1e-7` | Exponential notation triggered for values $< 10^{-6}$; lowercase `'e'`, no leading zero. |
| **NUM-04** | Zero float | `0.0` | `0` | Serialized as integer zero (RFC 8785 3.2.2.3). |
| **NUM-05** | Integer formatted with trailing zero | `1.0` | `1` | Trailing `.0` omitted. |
| **NUM-06** | Large integer exponential threshold ($10^{20}$) | `100000000000000000000` | `100000000000000000000` | Standard decimal up to $10^{20}$. |
| **NUM-07** | Large exponential threshold ($10^{21}$) | $10^{21}$ | `1e+21` | Lowercase `'e'`, explicit `+`, no leading zeros. |
| **NUM-08** | Not-a-Number literal | `NaN` | Rejected (`400`) | Returns HTTP 400 `NON_FINITE_NUMERIC_TOKEN`. |
| **NUM-09** | Positive infinity | `Infinity` | Rejected (`400`) | Returns HTTP 400 `NON_FINITE_NUMERIC_TOKEN`. |
| **NUM-10** | Negative infinity | `-Infinity` | Rejected (`400`) | Returns HTTP 400 `NON_FINITE_NUMERIC_TOKEN`. |

---

### Category 5: Framing, Duplication, and Structural Validation

| Test ID | Description / Input | Canonicalizer Result | Ingestion HTTP Status | Expected Error Code | Acceptance Criterion |
|---|---|:---:|:---:|---|---|
| **FRAME-01** | Payload exactly 1,048,576 bytes ($1\text{ MiB}$) | **Accepted** | `202` | None | Ingested successfully into proposed PostgreSQL `BYTEA`. |
| **FRAME-02** | Payload exactly 1,048,577 bytes ($1\text{ MiB} + 1\text{ B}$) | **Rejected** | `413` | `PAYLOAD_TOO_LARGE` | Connection severed, rejected at streaming boundary. Proposed transport mapping. |
| **FRAME-03** | Top-level array: `[1, 2, 3]` | **Rejected** | `400` | `TOP_LEVEL_OBJECT_REQUIRED` | Root must be JSON Object. Returns HTTP 400 per HR-IDEM-002. |
| **FRAME-04** | Top-level string: `"hello"` | **Rejected** | `400` | `TOP_LEVEL_OBJECT_REQUIRED` | Root must be JSON Object. Returns HTTP 400 per HR-IDEM-002. |
| **FRAME-05** | Top-level primitive (`true`, `false`, `null`, `123`) | **Rejected** | `400` | `TOP_LEVEL_OBJECT_REQUIRED` | Root must be JSON Object. Returns HTTP 400 per HR-IDEM-002. |
| **FRAME-06** | Duplicate key identical literals: `{"a": 1, "a": 2}` | **Rejected** | `400` | `DUPLICATE_OBJECT_KEY` | Rejection on duplicate key detection. Returns HTTP 400 per HR-IDEM-002. |
| **FRAME-07** | Duplicate key via escape: `{"a": 1, "\u0061": 2}` | **Rejected** | `400` | `DUPLICATE_OBJECT_KEY` | Evaluated after escape decode. Returns HTTP 400 per HR-IDEM-002. |
| **FRAME-08** | Unsupported compression: `Content-Encoding: gzip` | N/A | `415` | `UNSUPPORTED_MEDIA_TYPE` | Non-identity encoding rejected. Unresolved authority question. |
| **FRAME-09** | Invalid content type: `Content-Type: text/plain` | N/A | `415` | `UNSUPPORTED_MEDIA_TYPE` | Must be `application/json`. Unresolved authority question. |

---

### Category 6: Concurrency & Idempotency Transaction Recovery (`HR-CANON-005`, `HR-IDEM-002`)

| Test ID | Concurrency Scenario | Ingoing Request State | Expected Behavior | Acceptance Criterion |
|---|---|---|---|---|
| **IDEM-01** | Sequential identical retry | Key $K$, identical payload $P$ | **HTTP 200 OK** | Returns original event acceptance body from first submission with header `Idempotent-Replay: true`. Never returns 202. |
| **IDEM-02** | Sequential key reuse with modified payload | Key $K$, altered payload $P'$ | **HTTP 409 Conflict** | Error code `IDEMPOTENCY_KEY_FINGERPRINT_MISMATCH`. No event created. |
| **IDEM-03** | Concurrent simultaneous duplicates on new key | Both send Key $K$, Payload $P$ | Request 1 (Winner): **HTTP 202 Accepted**<br>Request 2 (Duplicate): **HTTP 200 OK** | Winner creates event (202). Loser catches `UniqueViolation`, executes immediate rollback, opens fresh transaction, re-reads winning row, returns original acceptance body (200). Never returns 202 for duplicate; never returns 500. |
| **IDEM-04** | Concurrent conflicting payload race on new key | Both send Key $K$, but $P_1 \ne P_2$ | Winner: **HTTP 202 Accepted**<br>Loser: **HTTP 409 Conflict** | Winner claims key (202). Loser catches `UniqueViolation`, rolls back, opens fresh transaction, detects fingerprint mismatch, returns `HTTP 409`. |
| **IDEM-05** | **Concurrent expired-key replacement (Same Payload)** *(Mandatory Condition)* | Two concurrent requests send Key $K$ (`expires_at <= statement_timestamp()`) and identical payload $P$ | Exactly one new Event created; exactly one replacement claim created.<br>Winner: **HTTP 202 Accepted** (or 200)<br>Loser: **HTTP 200 OK** | Request 1 acquires `FOR UPDATE`, retires expired record (`retired_at = statement_timestamp()`), inserts replacement claim, and creates Event. Request 2 catches `UniqueViolation` on partial index, rolls back, opens fresh transaction, re-reads winning active record, and returns HTTP 200. **Two competing requests never create duplicate Events. Zero HTTP 500.** |
| **IDEM-06** | **Concurrent expired-key replacement (Different Payload)** *(Mandatory Condition)* | Two concurrent requests send Key $K$ (`expires_at <= statement_timestamp()`) but $P_1 \ne P_2$ | Winner: **HTTP 202 Accepted** (or 200)<br>Loser: **HTTP 409 Conflict** | Winner replaces key and creates Event. Loser catches `UniqueViolation`, rolls back, opens fresh transaction, detects fingerprint mismatch against new active record, and returns HTTP 409. Zero duplicate Events created. |
| **IDEM-07** | Bounded Lock Waiting Under Contention | Multiple concurrent requests under lock contention | Winner: `202 Accepted`<br>Others: `200 OK` | Bounded lock timeout (TBD, testing 500ms and 2s benchmarks). Zero hung connections, zero deadlocks, zero 500 errors. |
| **IDEM-08** | Incomplete Record Visibility Guard | Winning transaction aborted prior to commit | Incoming request on Key $K$ | **HTTP 202 Accepted** | Uncommitted row is discarded by PostgreSQL MVCC; incoming request claims key cleanly. Incomplete records (`response_body IS NULL`) are never externally visible. |
