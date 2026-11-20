# HookRelay — M0 Engineering Foundation

HookRelay is a high-performance, production-oriented webhook delivery engine.

This repository establishes the **Milestone 0 (M0)** engineering foundation, providing a reproducible development environment, strict architectural boundaries, automated quality gates, database connectivity, and testing infrastructure.

---

## 1. Technology Baseline

| Component | Technology | Version / Specification |
|---|---|---|
| Language | Python | `3.14.8` (pinned in `.python-version`) |
| Package & Environment Manager | `uv` | Locked with `uv.lock` in frozen mode |
| Web Framework | FastAPI | `>=0.115.0` with Uvicorn ASGI |
| Database | PostgreSQL | 18+ (tested against live instance) |
| Async Driver | asyncpg / psycopg3 | High-performance async connection |
| ORM | SQLAlchemy 2.x | Explicit async session lifecycle & transactions |
| Migrations | Alembic | Fully async schema migration runner |
| Cache / Queue Boundary | Redis | `redis-py` async integration boundary |
| Configuration & Validation | Pydantic v2 & Pydantic Settings | Environment-driven, strict production validation |
| Test Framework | Pytest | `pytest-asyncio` with real PostgreSQL integration tests |
| HTTP Client | HTTPX | Used for test transport and outbound calls |
| Code Quality & Linter | Ruff | Formatting, isort, pyflakes, pyupgrade |
| Type Checker | Mypy | Strict static type checking across boundaries |
| Containerization | Docker | Multi-stage slim image with non-root user |

---

## 2. Architecture Boundaries

The application is structured around strict architectural separation:

```text
hookrelay/
├── app/
│   ├── main.py              # Application entrypoint & lifespan hooks
│   ├── api/                 # HTTP routing layer
│   │   ├── router.py        # Versioned route registry
│   │   └── v1/
│   │       └── health.py    # Liveness and readiness endpoints
│   ├── core/                # Core infrastructure
│   │   ├── config.py        # Pydantic Settings & environment validation
│   │   ├── logging.py       # Structured logging setup
│   │   └── exceptions.py    # Domain & infrastructure exception hierarchy
│   ├── db/                  # Database connectivity & session handling
│   │   ├── base.py          # SQLAlchemy DeclarativeBase
│   │   └── session.py       # Async engine, sessionmaker, transaction lifecycle
│   ├── models/              # Persistence models (no business entities in M0)
│   ├── schemas/             # Pydantic request/response schemas
│   ├── repositories/        # Database access layer boundary
│   │   └── base.py          # Generic base repository
│   ├── services/            # Business operations & orchestration
│   │   └── health.py        # System health inspection service
│   ├── workers/             # Async background workers (deferred to M1+)
│   └── integrations/        # External infrastructure boundary (Redis, HTTP)
│       └── redis.py         # Redis client encapsulation
├── migrations/              # Alembic migration scripts
│   ├── env.py               # Async Alembic execution environment
│   └── versions/            # Versioned migration scripts
├── tests/                   # Automated test suite
│   ├── conftest.py          # Shared fixtures (real PostgreSQL engine, client)
│   ├── unit/                # Fast unit tests (config, schemas, liveness)
│   └── integration/         # Integration tests (PostgreSQL, Alembic migrations)
├── .env.example             # Safe environment variable template
├── .gitignore               # Strict exclusion of secrets and build caches
├── .python-version          # Pinned Python runtime version
├── alembic.ini              # Alembic configuration
├── pyproject.toml           # Project dependencies and tool configurations
├── uv.lock                  # Deterministic dependency lockfile
├── Dockerfile               # Production container image specification
└── README.md                # Project documentation
```

### Boundary Rules
- **API layer** handles HTTP requests/responses and invokes services; route handlers never access the database directly.
- **Service layer** coordinates business logic and transaction boundaries.
- **Repository layer** isolates database queries and persistence details.
- **Integrations layer** encapsulates external systems (Redis, outbound HTTP).
- **Zero Secrets**: Secrets and credentials are never checked into Git.

---

## 3. Local Development Setup

### Prerequisites
- Python `3.14.8` (or version matching `.python-version`)
- `uv` package manager (`pip install uv` or standalone installer)
- PostgreSQL 18+ server running locally or via Docker

### Quick Start

1. **Clone and navigate to repository:**
   ```bash
   git clone <repo-url>
   cd webhook
   ```

2. **Create virtual environment and install locked dependencies:**
   ```bash
   uv venv .venv
   uv sync --frozen
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to configure your PostgreSQL credentials (e.g. `DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/hookrelay`).

4. **Run database migrations:**
   ```bash
   .\.venv\Scripts\alembic upgrade head
   # On Linux/macOS:
   # .venv/bin/alembic upgrade head
   ```

5. **Start development server:**
   ```bash
   .\.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   - OpenAPI documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - Liveness probe: [http://127.0.0.1:8000/api/v1/health/live](http://127.0.0.1:8000/api/v1/health/live)
   - Readiness probe: [http://127.0.0.1:8000/api/v1/health/ready](http://127.0.0.1:8000/api/v1/health/ready)

---

## 4. Verification and Quality Gates

All contributions must pass the following quality gates:

### Run Linter and Formatter
```bash
# Check code style and errors
.\.venv\Scripts\ruff check .

# Check formatting compliance
.\.venv\Scripts\ruff format --check .
```

### Run Type Checking
```bash
.\.venv\Scripts\mypy app
```

### Run Test Suite (Unit + PostgreSQL Integration)
Ensure the test database exists (e.g. `hookrelay_test`):
```bash
.\.venv\Scripts\pytest -v
```

---

## 5. Docker Deployment

Build and run the container:
```bash
# Build image
docker build -t hookrelay:latest .

# Run container with environment configuration
docker run -d --name hookrelay -p 8000:8000 --env-file .env hookrelay:latest
```

---

## 6. M0 Acceptance Criteria Status

- [x] Repository structure established according to approved specification.
- [x] Application starts cleanly via FastAPI and Uvicorn.
- [x] Configuration validation with Pydantic Settings fails fast on invalid configs and prevents unsafe defaults.
- [x] Database connectivity verified with real PostgreSQL instance.
- [x] Alembic migration runner verified (upgrading and downgrading test migration).
- [x] Pytest executes 13/13 passing tests (unit tests and PostgreSQL integration tests).
- [x] Ruff linting and formatting pass with 0 errors.
- [x] Mypy strict type checking passes on `app` with 0 errors.
- [x] No secrets or credentials committed to Git.
- [x] Deterministic dependencies locked in `uv.lock` and pinned in `.python-version`.
