# HookRelay M1 Gate 1 — Technical Specification
# Document 01: Canonicalization Technical Contract

- **Document Version:** 1.3.0
- **Milestone:** M1 — Event Ingestion & Idempotency Engine
- **Gate:** 1 — Technical Contract & Architecture Specification
- **Status:** Complete — Revised per Anna Independent Review & Odin Final Requirements
- **Traceability:** RFC 8785 (JCS), HR-IDEM-001, HR-IDEM-002, HR-CANON-001 through HR-CANON-005

---

## 1. Executive Summary & Architecture Separation

This contract establishes the normative technical specifications for payload processing, JSON canonicalization, and payload fingerprinting in HookRelay.

### 1.1. Separation of Concerns: Canonicalizer Engine vs. HTTP Ingestion Layer
To prevent coupling transport concerns with core data transformation, HookRelay strictly separates the canonicalizer from the HTTP transport layer:
1. **Canonicalizer Engine (Pure Domain Component):** Operates strictly on byte streams and JSON tokens. It returns a deterministic domain result:
   - `CanonicalizerResult::Ok { canonical_bytes: bytes, fingerprint: str }`
   - `CanonicalizerResult::Err { error_type: CanonicalizationError, details: str }`
   The canonicalizer has no knowledge of HTTP protocols, status codes, or connection state.
2. **HTTP Ingestion Layer (Transport Adapter):** Receives HTTP requests, streams the body, invokes the canonicalizer, and maps any input or canonicalization errors to HTTP transport responses. Per previously approved **`HR-IDEM-002`**, all invalid JSON client inputs map to **`HTTP 400 Bad Request`**.

---

## 2. Ingestion Boundaries & Framing Constraints

All incoming ingestion requests must satisfy the following transport prerequisites before canonicalization:

| Constraint ID | Parameter | Normative Requirement | Failure Mode (HTTP Ingestion Layer) | Authority |
|---|---|---|---|---|
| **ING-FRAME-01** | **Transport Method** | `POST` only. All other HTTP methods must be rejected. | HTTP 405 Method Not Allowed | Standard HTTP Transport |
| **ING-FRAME-02** | **Content-Type** | Must be `application/json` (or `application/json; charset=utf-8`). | HTTP 415 Unsupported Media Type | Unresolved authority question; pending explicit founder approval |
| **ING-FRAME-03** | **Content-Encoding** | Compression algorithms (e.g. `gzip`, `deflate`, `br`) are unsupported in v1. | HTTP 415 Unsupported Media Type | Unresolved authority question; pending explicit founder approval |
| **ING-FRAME-04** | **Maximum Size** | Exactly **1 MiB** ($1,048,576$ bytes). Size must be enforced strictly while streaming chunks; terminates immediately upon reading byte $1,048,577$. | HTTP 413 Payload Too Large (`PAYLOAD_SIZE_EXCEEDED`) | Proposed transport mapping; pending explicit founder approval |
| **ING-FRAME-05** | **Raw Payload Storage** | The exact byte sequence received over the wire must be captured in memory/spool and written unchanged to storage. | N/A (Fidelity Requirement) | `HR-IDEM-001` (Storage mechanism proposed: PostgreSQL `BYTEA`, pending Founder approval) |

---

## 3. RFC 8785 (JCS) Normative Rules

The canonicalization algorithm must follow RFC 8785 without alteration:

### 3.1. Character Encoding
- Input payload must be valid UTF-8 without Byte Order Mark (BOM).
- Leading BOM (`EF BB BF`) is strictly prohibited and rejected.
- Canonical output is an invariant UTF-8 byte stream.

### 3.2. Whitespace Elimination
- All insignificant whitespace characters outside JSON string literals (`0x20` SPACE, `0x09` HORIZONTAL TAB, `0x0A` LINE FEED, `0x0D` CARRIAGE RETURN) must be stripped.
- Structural tokens (`{`, `}`, `[`, `]`, `:`, `,`) must have no surrounding whitespace.

### 3.3. Property Sorting
- Object member keys must be sorted lexicographically by comparing the UTF-16 code units of their member names (equivalent to comparing scalar Unicode code points for valid Unicode, matching byte-by-byte comparison of their UTF-8 representation).
- Sorting is case-sensitive (ASCII byte value ordering: uppercase before lowercase).

### 3.4. String Serialization & Escaping
- String literals must be enclosed in standard double quotes (`"`).
- Escaping is permitted **only** for:
  1. Quotation mark (`"` -> `\"`, `0x5C 0x22`)
  2. Reverse solidus (`\` -> `\\`, `0x5C 0x5C`)
  3. Control characters `U+0000` through `U+001F` (`\u00xx` using lowercase hexadecimal digits).
- The solidus (`/`) character **MUST NOT** be escaped.
- All other Unicode characters (including `U+007F` through `U+10FFFF`) must be serialized as raw UTF-8 octets, never as `\uXXXX` escape sequences.

---

## 4. Resolution of the Five Identified Canonicalization Defects

### 4.1. Defect 1: JSON Nesting Depth Enforcement (`HR-CANON-001`)

- **Vulnerability/Problem:** Deeply nested JSON objects or arrays trigger stack exhaustion (`RecursionError`) in recursive-descent parsers, causing Denial of Service (DoS).
- **Canonicalizer Domain Specification:**
  - Maximum permitted nesting depth is **32**.
  - Depth counting starts at **1** with the root JSON object:
    - Root object `{}` = depth 1.
    - `{"a": {}}` = depth 2.
    - `{"a": [{"b": ...}]}`: each container (object or array) increments depth by 1.
  - **Depth 32 is valid and accepted** by the canonicalizer engine.
  - **Depth 33 is strictly rejected** by the canonicalizer engine.
- **Enforcement Mechanism:**
  - Depth tracking must occur inside the SAX-style or pull-parser lexer token stream before allocating nested object trees in memory.
- **HTTP Ingestion Mapping (per HR-IDEM-002):**
  - HTTP Status: `400 Bad Request`
  - Error Code: `PAYLOAD_NESTING_DEPTH_EXCEEDED`
  - Response Message: `"JSON nesting depth exceeds the maximum allowed limit of 32."`

### 4.2. Defect 2: Unsafe Integer Range Enforcement (`HR-CANON-002`)

- **Vulnerability/Problem:** JSON integers outside the IEEE 754 double-precision exact integer range lose precision when ingested or transferred to systems that parse JSON numbers into IEEE 754 64-bit floats. Silent rounding creates non-deterministic fingerprinting discrepancies.
- **Canonicalizer Domain Specification:**
  - Safe integer range: $[-(2^{53} - 1), +(2^{53} - 1)]$
  - Minimum safe integer: `-9007199254740991`
  - Maximum safe integer: `+9007199254740991`
  - Integer tokens within this range are accepted.
  - Any integer literal with $|n| > 9007199254740991$ must be rejected by the canonicalizer engine.
- **Enforcement Mechanism:**
  - Lexical parser inspects raw integer token strings before converting them into native types. Tokens exceeding 16 digits (or exceeding the boundary upon magnitude comparison) are rejected before precision loss occurs.
- **HTTP Ingestion Mapping (per HR-IDEM-002):**
  - HTTP Status: `400 Bad Request`
  - Error Code: `UNSAFE_INTEGER_RANGE_EXCEEDED`
  - Response Message: `"Integer token value is outside the safe range [-(2^53-1), 2^53-1]."`

### 4.3. Defect 3: Unicode & Surrogate Pair Validation (`HR-CANON-003`)

- **Vulnerability/Problem:** Lone surrogate code points (`U+D800` through `U+DFFF`) cannot be legally encoded into UTF-8 under RFC 3629. Some Python parsers and C libraries silently substitute replacement characters (`U+FFFD`) or produce invalid UTF-8 byte sequences.
- **Canonicalizer Domain Specification:**
  - Lone high surrogates (`U+D800`–`U+DBFF` not immediately followed by low surrogate) are strictly rejected.
  - Lone low surrogates (`U+DC00`–`U+DFFF` not preceded by high surrogate) are strictly rejected.
  - Reversed surrogate pairs (`\uDC00\uD800`) are strictly rejected.
  - Invalid UTF-8 octet sequences (e.g., overlong encodings `0xC0 0xAF`, orphan continuation bytes, invalid lead bytes `0xF5`–`0xFF`) must fail decoding immediately.
- **Enforcement Mechanism:**
  - Strict UTF-8 decoder with error handler `surrogatepass=False` and explicit escape-sequence scanner for `\uD800`–`U+DFFF`.
- **HTTP Ingestion Mapping (per HR-IDEM-002):**
  - HTTP Status: `400 Bad Request`
  - Error Code: `INVALID_UNICODE_SEQUENCE`
  - Response Message: `"Payload contains invalid UTF-8 or unassigned/lone Unicode surrogate code points."`

### 4.4. Defect 4: Numeric Serialization & ECMA-262 Conformance (`HR-CANON-004`)

- **Vulnerability/Problem:** RFC 8785 Section 3.2.2.3 mandates that floating-point numbers be serialized following ECMAScript (ECMA-262) `Number::toString()`. Python's `repr()` and `json.dumps()` violate ECMA-262 formatting rules.
- **Normative Serialization Rules & Required Examples:**
  
  | Input | Expected Canonical Representation | Rule Justification |
  |---|---|---|
  | `-0.0` | `0` | Sign stripped; negative zero must serialize as integer zero per ECMA-262 7.1.12.1. |
  | `1e-6` | `0.000001` | Non-exponential decimal notation used for values in range $[10^{-6}, 10^{21})$. |
  | `1e-7` | `1e-7` | Exponential notation triggered for values $< 10^{-6}$; lowercase `'e'`, no leading zero in exponent. |

- **Library Evaluation Criteria (Mandatory Gate 2 Evaluation Protocol):**
  - HookRelay **will not assume an external library is compliant merely because it claims RFC 8785 support**.
  - **Empirical Evaluation Mandate:** In Gate 2, maintained Python JCS implementations (e.g. `rfc8785`, `jcs`) must be evaluated directly against the official `cyberphone/json-canonicalization` reference corpus, including all edge cases in `number-formatting.json` and the explicit examples above.
  - **Adoption Standard:** If an existing maintained package passes 100% of the reference suite and satisfies HookRelay boundary constraints, it will be adopted.
  - **Custom Implementation Restriction:** A custom serializer or compiled C/Rust extension will **NOT** be introduced unless library evaluation demonstrates that maintained packages fail reference vectors, and any such proposal is explicitly documented and approved.
- **HTTP Ingestion Mapping for Non-Finite Numbers (per HR-IDEM-002):**
  - HTTP Status: `400 Bad Request`
  - Error Code: `NON_FINITE_NUMERIC_TOKEN`
  - Response Message: `"Numeric values NaN, Infinity, and -Infinity are forbidden."`

### 4.5. Defect 5: SQL Transaction & Idempotency Conflict Recovery (`HR-CANON-005`)

- **Detailed in Document 02:** Fully specified in [02_idempotency_transaction_concurrency_contract.md](file:///E:/Projects/personal/webhook/docs/m1/02_idempotency_transaction_concurrency_contract.md).

---

## 5. Preserved Ingestion Constraints

### 5.1. Top-Level Structure
- The root of the JSON payload must be an **Object** (`{ ... }`).
- Top-level arrays (`[ ... ]`), strings, numbers, booleans, or null are rejected.
- HTTP Status: `400 Bad Request` (per `HR-IDEM-002`)
- Error Code: `TOP_LEVEL_OBJECT_REQUIRED`

### 5.2. Duplicate Key Detection After Escape Decoding
- JSON objects containing duplicate keys must be rejected.
- Key equality is evaluated **after** Unicode and JSON escape resolution:
  - Example: `{"\u0061": 1, "a": 2}` resolves both keys to `"a"`.
- Must be rejected during parsing before canonical sorting.
- HTTP Status: `400 Bad Request` (per `HR-IDEM-002`)
- Error Code: `DUPLICATE_OBJECT_KEY`

### 5.3. Cryptographic Fingerprint Specification
- **Algorithm:** SHA-256 (NIST FIPS 180-4).
- **Fingerprint Scheme Identifier:** `jcs-rfc8785-v1`
- **Output Format:** Lowercase hexadecimal string prefixed with the identifier:
  $$\text{Fingerprint} = \text{"jcs-rfc8785-v1:"} \parallel \text{HEX}(\text{SHA-256}(\text{CanonicalBytes}))$$
- **Length:** 79 characters total (`14` prefix + `64` hex characters).
- Example: `jcs-rfc8785-v1:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
