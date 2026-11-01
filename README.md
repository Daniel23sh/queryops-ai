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
  │     → SemanticPlan validation and selected-definition/relational checks
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

Approved query templates bypass the LLM provider. Free-text queries use the current plan-only provider contract, which returns a structured `SemanticPlan` in one call. After validating that plan, the backend renders SQL deterministically. Free-query language interpretation belongs to the planner. Lexical/structural matches supply non-binding candidates and Suggested Intent. Selected catalog definitions and deterministic relational/security checks remain binding. Required Intent is fail-closed only when supplied by an independently trusted structured source; ordinary free questions currently have no such source.

The backend-rendered SQL remains untrusted and must pass every downstream control before execution.

## Key Capabilities

- **Natural-language and template queries:** Run free-text questions when permitted or use approved, provider-free query templates.
- **Semantic planning:** Supply safe candidates from a versioned IT Operations Semantic Catalog; one provider interprets the question as a typed plan. Lexical/structural hints are guidance, while selected business definitions and deterministic relational/security checks remain binding.
- **Governed execution:** Validate structured plans and read-only SQL, check SQLGlot semantic conformance, and execute only sanitized SQL through a restricted PostgreSQL runtime role.
- **Scope-aware access:** Apply effective permissions, assigned scopes, role-aware SQL visibility, and PostgreSQL Row-Level Security (RLS).
- **Dashboards and visualizations:** Save successful query runs as cards, arrange responsive dashboards, refresh under the current viewer's scope, and render supported table, KPI, chart, gauge, and status views.
- **Result delivery:** Preserve query-bound provenance through saved Cards and CSV. Partial or unknown delivery is disclosed separately from visualization previews; Table Cards can expand all already-returned rows. CSV downloads retain ordinary data records and identify delivery limitations in response metadata, filename and UI.
- **Output identity:** Backend-rendered fields retain distinct values under unique deterministic labels. Ambiguous legacy SQL fails safely; affected saved Cards must be regenerated from an authorized fresh query. See the [output identity contract](docs/development/semantic-ownership-migration.md#deterministic-output-identity--m10-w6b-contract).
- **Controlled export:** Revalidate and re-execute eligible reports for CSV export under current-viewer authorization, with sanitization and audit records.
- **Governed operational actions:** Preview, request, approve, synchronously execute, and audit `reclaim_unused_license` and `disable_inactive_user` through deterministic handlers.
- **Workflow visibility:** Provide requester action tracking, approval queues, scoped audit views, and database-backed notifications.
- **Evaluation infrastructure:** Measure Query Engine behavior with a fixed IT Operations dataset, sanitized persisted results, role-aware read-only metrics, and a fail-closed readiness assessment.

## Governance and Security

Authorization is enforced by the backend and database; frontend capability checks are usability controls, not the security boundary.

- `UserAccessContext` combines effective permissions with assigned department or global scopes.
- Dashboard department affiliation is metadata, not a grant: departmental access requires an explicit matching or global assignment. Personal ownership remains separate.
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

The supported V1 target is local use with synthetic data. The checked-in environment is for that target; changing credentials alone does not provide real authentication or make shared/production deployment supported.

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

Evaluation environment v2 binds evidence to the exact provider behavior settings
and installed runtime versions. Manifest preparation and evaluation must use the
same configuration; read-only readiness checks the current OpenAI candidate
settings without requiring a key. Old or missing identity evidence is incomplete.
Logical calls, measured HTTP attempts and unavailable usage are reported separately.
See the [identity and qualification contract](docs/evaluation/v1-quality-gates.md#environment-identity-and-invalidation).

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

Some backend security and RLS tests require PostgreSQL and intentionally skip without a disposable test database. The state-changing `@m8-primary` browser flows also require isolated disposable database preparation. GitHub Actions runs the authoritative deterministic gates across backend tests, an isolated PostgreSQL security suite, frontend checks, general browser flows, and state-changing action/access workflows. See the [validation commands and fixture order](docs/development/validation-model.md#browser-and-cross-layer-flows).

## Project Status

The core Query Engine, Ask Data workspace, dashboard and export flows, scope-aware authorization, PostgreSQL RLS, two governed IT Operations actions, approvals, audit views, notifications, and evaluation/readiness infrastructure are implemented.

The active milestone is **M10 — Product Reliability & V1 Completion**, targeting a complete local IT Operations V1 with synthetic data. Demo authentication is the only usable auth mode; actions are synchronous, notifications database-only, and the action catalog has two workflows. Shared/production deployment and major new capabilities are separate future scope.

The [October audit](docs/audits/2026-10-26-project-audit-he.md) verified substantial functionality while reproducing scope-revocation, concurrent role-request, scoped Evaluation read, result-delivery and UI defects. Its single live canary passed 9/10 and is diagnostic only. Automated readiness and full manual release QA remain incomplete. The architecture is being preserved; remaining work follows the [M10 roadmap](docs/development/m10-completion-roadmap.md), with current approval, branch/merge status and next work only in [PROJECT_PLAN.md](PROJECT_PLAN.md). W0 integrated the reviewed bounded-result baseline through [PR #61](https://github.com/Daniel23sh/queryops-ai/pull/61). The repository is not release-ready.

## Maintainer

Maintained by [Daniel23sh](https://github.com/Daniel23sh).

## License

No license has been selected for this repository.
