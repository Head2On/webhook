# HookRelay M0 — Updated Odin Review & Anna Requirements

**Branch:** `feature/m0-engineering-foundation`  
**Status:** PASS WITH CONDITIONS  
**Scope:** Correct M0 only. Do not implement M1 or any business functionality.

## 1. Exact dependency pinning

- Replace every direct dependency range in `pyproject.toml` with an exact `==` version.
- Apply this to development dependencies too.
- Preserve currently selected versions unless a concrete compatibility issue requires a change.
- Regenerate `uv.lock`.
- Delete `.venv` and demonstrate a fresh installation using:

```bash
uv sync --frozen
```

- Verify CI lockfile consistency.
- Include the exact dependency versions in the completion report.

## 2. PostgreSQL test isolation

Provide implementation and evidence that:

- Integration tests use a dedicated test database.
- Destructive migration operations cannot accidentally run against development or production databases.
- The database name comes from environment configuration, not a hardcoded production-like URL.
- Migration lifecycle tests are repeatable.
- Baseline marker and Alembic state are properly cleaned up.
- Concurrent test runs cannot interfere with one another.

**Required demonstrations:**

1. Run the migration lifecycle test twice consecutively. Both runs must pass.
2. Run two test instances concurrently against differently named test databases. Both must pass.
3. Show the environment variable and database naming mechanism.
4. Show the cleanup logic.

Do not introduce Testcontainers unless technically necessary and justified.

## 3. Python runtime consistency

- Change `.python-version` from `3.14.8` to `3.14`.
- Keep `requires-python` as a compatibility range: `>=3.14,<3.15`.
- Pin the Dockerfile base image to a specific Python 3.14 patch version.
- Demonstrate a fresh installation on the selected runtime.

## 4. Baseline migration verification

Provide the complete contents of:

`migrations/versions/0001_initial_baseline.py`

Acceptable:
- Empty baseline migration.
- Marker-table-only migration.

Unacceptable:
- Any business tables or entities intended for M1 or later.

No business database entities may be introduced in M0.

## 5. Environment credential verification

Provide the complete contents of `.env.example`.

Verify that it contains only safe example values or placeholders.

No real:
- PostgreSQL credentials
- Redis credentials
- KMS credentials
- API keys or other secrets

## 6. Scope verification

Provide:

- `git diff --stat` from `main` to `feature/m0-engineering-foundation`.
- Output of:

```bash
rg -i 'idempotency|delivery|dlq|tenant|event|webhook' app/ migrations/
```

Any matches must be inspected. Only comments explaining exclusions are acceptable; no M1 business implementation.

Confirm that no M1 functionality was introduced.

## 7. Quality verification

Report results for:

- `uv sync --frozen`
- Ruff check and formatting
- Mypy
- Complete Pytest suite
- PostgreSQL integration tests
- Alembic migration lifecycle tests

Include actual command outputs or concise, verifiable evidence.

## 8. Completion report

Include:

1. Changed files and implementation summary.
2. Exact dependency versions and lockfile validation.
3. Fresh environment installation evidence.
4. PostgreSQL test isolation evidence.
5. Python runtime and Docker consistency.
6. Ruff, Mypy, and Pytest results.
7. Confirmation that no M1 functionality was introduced.
8. Complete contents of `0001_initial_baseline.py`.
9. Complete contents of `.env.example`.
10. `git diff --stat` against `main`.
11. Business-identifier search output.

## Final instruction

Address only these M0 review findings and Anna's additional requirements.

Do not begin M1. Do not introduce business functionality.

Stop after corrections and provide the complete evidence report for Odin and Anna's independent verification. Await founder approval.