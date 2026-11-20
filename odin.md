# HookRelay — M0 Implementation Assignment
**Version:** 0.2  
**Status:** Founder-authorized  
**Technical Lead:** Odin  
**Independent Reviewer:** Anna

## Objective

Implement the HookRelay engineering foundation according to the founder-approved M0 specification.

### 1. Technology requirements

- Python — exact runtime version pinned in `.python-version`
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL
- Alembic
- Pydantic v2
- Redis integration boundary
- Pytest
- HTTPX
- Ruff
- Mypy
- uv for dependency management

### 2. Mandatory requirements

1. Initialize the Git repository and approved directory structure.
2. Configure `pyproject.toml` and commit `uv.lock`.
3. Pin the Python runtime version in `.python-version`.
4. **All direct and transitive dependencies must be resolved to exact versions in the committed `uv.lock`; CI and deployment installations must use the lockfile in frozen mode, and CI must fail if the lockfile is inconsistent with project dependencies.**
5. Implement application configuration and validation.
6. Create the FastAPI application entry point.
7. Establish SQLAlchemy database session management.
8. Configure Alembic migrations.
9. Establish unit and integration test foundations.
10. Configure linting, formatting and type checking.
11. Write README instructions for reproducible development.

### 3. Architecture boundaries

- API layer handles HTTP requests and responses.
- Service layer owns business operations and transaction orchestration.
- Repository layer handles database access.
- Models represent persistence structures.
- Schemas define request and response contracts.
- Workers execute asynchronous background processing.
- Integrations isolate infrastructure dependencies.

Do not introduce business features or invent database entities during M0.

### 4. Canonicalizer debt — tracked

The existing HR-IDEM-001 decision requires:

- RFC 8785 JSON Canonicalization Scheme.
- SHA-256 fingerprinting.
- Original raw payload preserved separately.
- Outbound HMAC signing uses original raw payload bytes.

The fingerprint identifier inconsistency remains tracked:

- `jcs-rfc8785-v1`
- `rfc8785-sha256-v1`

Do not resolve or implement the canonicalizer during M0. It must be resolved before event ingestion implementation begins.

### 5. Implementation constraints

- No tenant management.
- No API key authentication.
- No event ingestion.
- No idempotency implementation.
- No delivery workers.
- No retry processing.
- No DLQ.
- No HMAC signing.
- No credentials committed to Git.
- No unnecessary dependencies.
- No unapproved architecture changes.

### 6. Deliverables

Provide:

1. Working repository foundation.
2. Reproducible dependency installation.
3. Successful application startup.
4. Database connectivity.
5. Migration validation.
6. Passing unit tests.
7. Integration-test foundation.
8. Successful Ruff and Mypy checks.
9. README development instructions.
10. Completion report with files created, dependency versions, commands, test results, limitations and deviations.

### 7. Stop condition

Stop after M0.

Do not begin M1 or implement business features without Odin's technical review and founder authorization.

The completed repository and test report must be made available to Ishan and Anna for verification.