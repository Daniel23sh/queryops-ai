# QueryOps AI

[![CI](https://github.com/Daniel23sh/queryops-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Daniel23sh/queryops-ai/actions/workflows/ci.yml)

QueryOps AI is a governed conversational data workspace for asking questions over structured business data, saving useful results, and carrying approved operational changes through policy and audit workflows. It goes beyond a text-to-SQL demo by treating authorization, semantic correctness, database safety, and action governance as first-class runtime concerns.

The current domain implementation is IT Operations, backed by deterministic synthetic data for directory users, departments, licenses, devices, support tickets, access groups, security events, and related operational records.

## What It Does

QueryOps AI gives business and technical users a shared workflow for governed data access:

```text
Request
  ├── free-text question
  │     → authorized schema and semantic grounding
  │     → provider-generated SemanticPlan only
  │     → Required Intent and SemanticPlan validation
  │     → deterministic backend SQL rendering, safety, and conformance checks
  └── approved template
        → deterministic provider-free SQL
              │
              ▼
       resource authorization and scoped PostgreSQL execution under RLS
              │
              ▼
       result, visualization, dashboard card, or governed export

Eligible result
  → deterministic action preview
  → policy and approval
  → narrow backend execution
  → audit and notification records
```

Approved query templates bypass the LLM provider. Free-text queries use the current plan-only provider contract, which returns a structured `SemanticPlan` in one call. After validating that plan, the backend renders SQL deterministically. Deterministic grounding separates result semantics into:

- **Required Intent** — high-confidence requirements that are validated fail-closed.
- **Suggested Intent** — non-binding planner guidance that cannot independently reject an otherwise valid plan.

The backend-rendered SQL remains untrusted and must pass every downstream control before execution.

## Key Capabilities

- **Natural-language and template queries:** Run free-text questions when permitted or use approved, provider-free query templates.
- **Semantic planning:** Ground questions against a versioned IT Operations Semantic Catalog, mandatory business concepts, canonical metrics, and Required/Suggested result intent.
- **Governed execution:** Validate structured plans and read-only SQL, check SQLGlot semantic conformance, and execute only sanitized SQL through a restricted PostgreSQL runtime role.
- **Scope-aware access:** Apply effective permissions, assigned scopes, role-aware SQL visibility, and PostgreSQL Row-Level Security (RLS).
- **Dashboards and visualizations:** Save successful query runs as cards, arrange responsive dashboards, refresh under the current viewer's scope, and render supported table, KPI, chart, gauge, and status views.
- **Controlled export:** Revalidate and re-execute eligible reports for CSV export under current-viewer authorization, with sanitization and audit records.
- **Governed operational actions:** Preview, request, approve, synchronously execute, and audit `reclaim_unused_license` and `disable_inactive_user` through deterministic handlers.
- **Workflow visibility:** Provide requester action tracking, approval queues, scoped audit views, and database-backed notifications.
- **Evaluation infrastructure:** Measure Query Engine behavior with a fixed IT Operations dataset, sanitized persisted results, role-aware read-only metrics, and a fail-closed readiness assessment.

## Governance and Security

Authorization is enforced by the backend and database; frontend capability checks are usability controls, not the security boundary.

- `UserAccessContext` combines effective permissions with assigned department or global scopes.
- PostgreSQL RLS restricts operational reads and writes using transaction-local viewer context.
- The LLM sees an allowlisted projection of authorized schema and business semantics—not database rows, user identities, scope keys, credentials, evaluation baselines, or action targets.
- Backend-rendered SQL is accepted only after the backend enforces read-only syntax, allowed resources, limits, semantic-plan consistency, and SQL semantic conformance.
- Query execution uses a restricted non-owner, read-only PostgreSQL role.
- The LLM never mutates operational data. Actions use explicit selectors, deterministic previews, current-state revalidation, policy checks, approval rules, a narrowly privileged action role, and atomic audit/notification writes.
- Sensitive response fields, including SQL and evaluation diagnostics, are projected according to effective permissions.

## Architecture

```text
React + TypeScript frontend
        │
        ▼
FastAPI API
  ├── demo auth, sessions, CSRF, permissions, and scopes
  ├── Query Engine ── Mock/OpenAI provider abstraction
  ├── dashboards, refresh, visualization metadata, and export
  ├── Action Engine ── policy, approval, execution, audit, notifications
  └── evaluation runner, metrics, and readiness policy
        │
        ▼
SQLAlchemy + Alembic
        │
        ▼
PostgreSQL 16
  ├── product and IT Operations data
  ├── Row-Level Security
  └── restricted query and action runtime roles
```

The repository is a monorepo:

- `frontend/` contains the responsive React application.
- `backend/` contains the API, Query Engine, Action Engine, domain pack, evaluation services, migrations, and tests.
- `docs/` contains public QA, security, and evaluation documentation.

IT Operations is implemented as the first domain pack; the core query and action infrastructure remains separated from its domain-specific schema, semantic definitions, templates, and handlers.

## Tech Stack

- **Frontend:** React, TypeScript, Vite, React Router, Tailwind CSS, Recharts, dnd-kit, React Grid Layout
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLGlot
- **Data:** PostgreSQL 16, psycopg, deterministic Faker-based seed profiles
- **AI:** Provider abstraction with deterministic MockLLM and explicit opt-in OpenAI Responses API support
- **Testing and tooling:** Pytest, Ruff, Pyright, Vitest, Testing Library, ESLint, Playwright, Docker Compose, GitHub Actions

## Local Development

### Prerequisites

- Docker with Docker Compose
- Git
- Optional for host-based development: Python 3.11+ and Node.js 22

### Docker quick start

From a fresh clone:

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed_it_operations.py --profile small --reset
```

Then open:

- Frontend: <http://localhost:5173>
- Backend health check: <http://localhost:8000/health>
- Interactive API docs: <http://localhost:8000/docs>

The login screen offers seeded Admin, Analyst, Manager, and User profiles so the permission and scope differences can be explored without external identity infrastructure.

Stop the stack without deleting the database volume:

```bash
docker compose down
```

The checked-in environment example is intended for local development. Replace `SESSION_SECRET_KEY` and database credentials before using the stack in any shared environment.

### Optional host-based development

Start PostgreSQL with Docker, then run the backend from the host:

```bash
docker compose up -d postgres

cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops
alembic upgrade head
python scripts/seed_it_operations.py --profile small --reset
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

## AI Provider

MockLLM is the normal development and CI default. It requires no network access or API key.

OpenAI is available only through explicit configuration:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=replace-with-a-local-secret
OPENAI_MODEL=gpt-5.6-terra
```

Setting `OPENAI_API_KEY` alone does not activate OpenAI. Real-provider requests can incur API charges; keep secrets out of tracked files and use MockLLM for routine development and tests.

The OpenAI provider returns only a structured `SemanticPlan` in one request. QueryOps validates the plan, renders SQL deterministically in the backend, and makes no repair or fallback provider call.

## Testing

Install dependencies once before running the local quality gates.

Run the standard non-destructive backend and frontend checks from the repository root:

```bash
./scripts/check
```

This uses `backend/.venv` directly. The individual commands remain available below for focused validation.

Backend:

```bash
cd backend
python -m pip install -e ".[dev]"
ruff check app scripts
pyright
python -m compileall -q app scripts
pytest
```

Offline semantic-ownership migration evidence (no provider or database), from
`backend/`: `.venv/bin/python -m scripts.audit_semantic_ownership`.
See the [PR53 experiment boundaries and findings](docs/development/semantic-ownership-migration.md).

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck:app
npm run typecheck:node
npm test
npm run build
```

With the Docker quick-start stack running, execute the general browser flows locally:

```bash
cd frontend
npx playwright install chromium
npx playwright test --grep-invert @m8-primary
```

Some backend security and RLS tests require PostgreSQL and intentionally skip without a disposable test database. The state-changing `@m8-primary` browser flow also requires its isolated disposable database preparation. GitHub Actions runs the authoritative deterministic gates across backend tests, an isolated PostgreSQL security suite, frontend checks, general browser flows, and the state-changing action workflow.

## Project Status

The core Query Engine, Ask Data workspace, dashboard and export flows, scope-aware authorization, PostgreSQL RLS, two governed IT Operations actions, approvals, audit views, notifications, and evaluation/readiness infrastructure are implemented.

The project remains under active V1 hardening. Text-to-SQL architecture and evaluation work continue, demo authentication is the only usable auth mode, actions execute synchronously, notifications are database-only, and the implemented action catalog is intentionally limited to two IT Operations workflows. Qualifying live-provider evidence has not been completed, so automated V1 readiness remains **incomplete**. Final manual QA is a separate release-completion requirement and is also open; the repository should not be treated as production-ready.

## Maintainer

Maintained by [Daniel23sh](https://github.com/Daniel23sh).

## License

No license has been selected for this repository.
