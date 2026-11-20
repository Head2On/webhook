# HookRelay — M0 Engineering Foundation Specification

**Owner:** Ishan, Founder  
**Technical Lead:** Odin  
**Independent Reviewer:** Anna  
**Implementation Assistant:** Antigravity

## 1. Objective

Establish a production-oriented backend foundation for HookRelay before implementing business features.

M0 must provide a maintainable application structure, reproducible development environment, consistent configuration, automated quality checks, and a reliable testing foundation.

## 2. Technology baseline

| Component | Technology |
|---|---|
| Language | Python |
| Backend framework | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.x |
| Database migrations | Alembic |
| Cache / rate limiting | Redis |
| Validation | Pydantic v2 |
| Testing | Pytest |
| HTTP client | HTTPX |
| Code quality | Ruff |
| Type checking | Mypy |
| Containerization | Docker |

Use compatible, explicitly pinned dependency versions. Do not install unnecessary packages.

## 3. Proposed repository structure

```text
hookrelay/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── router.py
│   │   └── v1/
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── exceptions.py
│   ├── db/
│   │   ├── session.py
│   │   └── base.py
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── services/
│   ├── workers/
│   └── integrations/
├── migrations/
│   └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── scripts/
├── docs/
├── .env.example
├── .gitignore
├── alembic.ini
├── pyproject.toml
├── README.md
└── Dockerfile
```

This is the proposed initial structure. Feature-specific modules will be introduced when their implementation begins.

## 4. Architecture boundaries

- API layer handles HTTP requests and responses.
- Service layer owns business operations and transaction orchestration.
- Repository layer handles database access.
- Models represent persistence structures.
- Schemas define external request and response contracts.
- Workers execute asynchronous background processing.
- Integrations isolate external infrastructure such as Redis, KMS and outbound HTTP.

Avoid circular dependencies and direct database access from route handlers.

## 5. Configuration and secrets

- Pydantic Settings for application configuration.
- Environment variables for deployment-specific settings.
- `.env.example` contains variable names and safe example values only.
- Real credentials must never enter Git.
- Separate development, test and production configuration.
- Fail startup when mandatory configuration is missing or invalid.
- Never silently fall back to insecure defaults.

## 6. Database foundation

- SQLAlchemy 2.x.
- Explicit session lifecycle management.
- Alembic for all schema migrations.
- Transaction boundaries must be visible and deliberate.
- No automatic schema creation in production.
- PostgreSQL integration tests must use a real PostgreSQL instance.

## 7. Testing and quality gates

Every contribution must pass:

1. Ruff linting.
2. Formatting checks.
3. Mypy checks for agreed application boundaries.
4. Pytest unit tests.
5. Relevant PostgreSQL integration tests.
6. Migration validation.
7. No committed secrets or environment-specific credentials.

Tests must verify behavior, not merely implementation details.

## 8. Development workflow

- Git-based version control.
- Feature branches for implementation work.
- Small, reviewable commits.
- No direct commits to the protected main branch.
- Every feature has acceptance criteria and tests.
- Antigravity must explain significant implementation choices.
- Odin reviews generated code before milestone closure.

## 9. M0 acceptance criteria

M0 is complete when:

- The repository structure is established.
- Application starts successfully.
- Configuration validation works.
- Database connectivity can be established.
- Alembic can create and apply a test migration.
- Pytest executes successfully.
- Ruff and type checks run successfully.
- No credentials are committed.
- README explains local development and testing.
- The development setup can be reproduced from documented instructions.

## 10. Explicit exclusions

M0 does not implement:

- Tenant management.
- API key authentication.
- Event ingestion.
- Idempotency.
- Delivery workers.
- Retry processing.
- DLQ.
- HMAC signing.

Those belong to subsequent implementation milestones.

## 11. Approval gate

This specification is a proposed engineering baseline, not authorization to implement.

Founder approval is required before Antigravity receives the M0 implementation assignment.