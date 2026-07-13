# QueryOps AI

QueryOps AI is planned as a governed conversational data workspace that will let users query structured business data in natural language, save insights as dashboards, and execute controlled operational actions through approval and audit workflows.

The project is being built to demonstrate how AI can be used not only to generate SQL, but also to support safe data exploration, reusable insights, permission-aware workflows, and auditable operational actions.

## Overview

Modern organizations often have valuable structured data stored in databases, but many business users cannot access it directly without help from analysts, developers, or IT teams.

QueryOps AI is designed to solve this with a controlled interface where users will be able to:

* ask questions about structured data in natural language
* receive SQL-backed results
* view explanations and assumptions
* save useful results as dashboard cards
* explore personal, shared, and scope-aware dashboards
* request operational actions based on query results
* route sensitive actions through approval flows
* keep a complete audit trail of important operations

The system is designed as a generic platform. The first implementation domain is IT Operations, but the core architecture should support additional domains in the future.

## First Domain: IT Operations

The first domain pack focuses on IT Operations data.

It uses synthetic but realistic operational data, including:

* departments
* directory users
* login events
* licenses
* license assignments
* devices
* software installs
* support tickets
* groups
* user group memberships
* security events
* IT audit events

Example questions the product should support:

* Which users have not logged in for more than 90 days and still have paid licenses?
* How many unused licenses exist by department?
* Which privileged users are inactive?
* Which devices are non-compliant or have outdated software?
* How many open support tickets exist by department and priority?
* Which terminated employees still have active accounts or assigned devices?

The IT Operations domain is only the first domain pack. Domain-specific tables, queries, dashboards, and actions should remain separate from the generic core engine.

## Core Product Flow

The intended product flow is:

```txt
Natural language question
→ safe SQL generation
→ SQL validation
→ scoped database execution
→ explained result
→ saved insight or dashboard card
→ suggested operational action
→ action preview
→ approval
→ execution
→ audit log
```

This makes QueryOps AI more than a text-to-SQL demo. It is designed as a governed operational data product.

## Main Capabilities

Planned V1 capabilities include:

* authentication and user onboarding
* role-based permissions
* natural-language data queries
* predefined query templates
* SQL generation and validation
* scoped query execution
* PostgreSQL Row-Level Security
* query history
* saved cards
* dashboard catalog
* personal, shared, and scope-aware dashboards
* controlled CSV export
* action recommendations
* action preview
* approval workflow
* notifications
* audit logs
* evaluation and testing screens

## User Roles

QueryOps AI is planned around four main roles.

### User

A regular user with limited read-only access.

Users can view approved dashboards, use approved templates, and access only the data they are allowed to see.

### Manager

A department-level business user.

Managers can ask natural-language questions about their department, view business-level insights, and create personal dashboards. They do not see raw SQL.

### Analyst

A technical department user.

Analysts can ask questions, view generated SQL, inspect query details, create department-level dashboard cards, and approve limited department actions according to policy.

### Admin

A global administrator.

Admins can manage users, approve role upgrades, access global data, manage global dashboards, approve sensitive actions, and view full audit and evaluation data.

## Architecture

QueryOps AI is planned as a monorepo with a separate frontend, backend, and database layer.

```txt
User Browser
→ React Frontend
→ FastAPI Backend
→ Auth and Permission Layer
→ Query Engine / Action Engine
→ PostgreSQL with RLS
→ Response Formatter
→ Dashboard / Tables / Charts
```

The frontend never communicates directly with the database or the LLM provider. All sensitive operations go through the backend, where authorization, validation, policy checks, and audit logging are enforced.

## Planned Tech Stack

### Frontend

* React
* TypeScript
* Vite
* React Router
* Tailwind CSS
* Lucide icons
* shadcn/ui
* Recharts
* dnd-kit

### Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy 2
* Alembic
* Pytest

### Database

* PostgreSQL
* Row-Level Security
* Alembic migrations
* deterministic synthetic seed data

### Authentication

Planned authentication modes:

* production-like mode using Supabase Auth with Google OAuth
* local demo mode using seeded demo users

Supabase is planned to handle external identity only. QueryOps AI manages its own application users, roles, departments, permissions, and approval policies.

### AI Layer

The backend should use an LLM provider abstraction.

The LLM should not execute SQL directly and should never perform database mutations. Any generated SQL must pass backend validation before execution.

Operational actions are executed only by deterministic backend logic after preview, policy checks, approval, and audit logging.

## Planned Repository Structure

```txt
queryops-ai/
  backend/
    app/
    tests/
    pyproject.toml

  frontend/
    src/
    package.json

  docs/
    planning/        # local/private planning documents, ignored by Git

  README.md
  PROJECT_PLAN.md
  AGENTS.md
  docker-compose.yml
  .env.example
  .gitignore
```

## Local Planning Documents

The full planning documents may exist locally under:

```txt
docs/planning/
```

These files are intentionally ignored by Git and are used as private implementation context when working with a local development agent.

Expected local planning files:

```txt
01-product-brief.md
02-mvp-prd.md
03-technical-architecture.md
04-it-operations-domain-pack.md
05-security-permissions-matrix.md
06-actions-approvals-audit.md
07-api-contract.md
08-ui-flows-wireframes.md
09-evaluation-testing-plan.md
10-development-milestones.md
```

The repository should remain usable without committing these private planning documents.

## Security Model

Security is a core part of the product design.

The planned security model includes:

* backend-managed permissions
* role-based and permission-based access control
* PostgreSQL Row-Level Security
* safe SQL validation
* restricted SQL visibility by role
* scoped query execution
* controlled CSV export
* action approval policies
* prevention of self-approval where required
* audit logging for sensitive operations
* limited LLM data exposure

The system should not rely on frontend visibility rules alone. The backend and database must enforce the actual access rules.

## Action and Approval Model

QueryOps AI is designed to support controlled operational actions.

Example V1 actions for the IT Operations domain:

* reclaim unused license
* disable inactive user

Actions follow a governed lifecycle:

```txt
suggested
→ preview
→ submitted for approval
→ approved or rejected
→ executed
→ audited
```

The LLM may suggest an action type, but it does not choose final records, approve changes, or mutate the database. The backend calculates the preview, checks eligibility, enforces policy, executes the operation, and writes audit logs.

## Evaluation and Testing

The project should include evaluation and testing for both regular software behavior and AI-assisted behavior.

Planned testing areas:

* backend API tests
* permission tests
* PostgreSQL RLS tests
* SQL validation tests
* query execution tests
* action authorization tests
* approval workflow tests
* audit tests
* CSV export tests
* frontend role-based rendering tests
* end-to-end demo flow tests
* mock LLM provider tests
* real LLM evaluation outside regular CI

Security-related tests should be treated as release-blocking.

## Local Development

Local development setup will use Docker Compose.

Copy the example environment file if you want local overrides:

```bash
cp .env.example .env
```

Start the local development stack:

```bash
docker compose up --build
```

This starts:

* PostgreSQL database
* FastAPI backend
* React frontend

Default local URLs:

* Frontend: `http://localhost:5173`
* Backend health endpoint: `http://localhost:8000/health`
* PostgreSQL: `localhost:5432`

PostgreSQL is included for the local development environment. Milestone 6 is complete and merged into `main`; the current application includes deterministic IT Operations seed data, demo auth, scope-aware PostgreSQL RLS, the backend Query Engine, the Ask Data frontend, dashboards and saved cards, controlled query/card CSV downloads, automatic/manual dashboard-card refresh, and persistent accessible card ordering. Milestone 7 is the active product UX milestone, and M7 PR1 is implementation-complete on `feature/m7-product-shell-navigation`. Actions, approvals, notifications, real LLM providers, Supabase Auth, and domain expansion remain planned for later milestones.

Stop the stack:

```bash
docker compose down
```

Remove the local PostgreSQL volume only when you intentionally want to reset local database state:

```bash
docker compose down -v
```

### Backend

The backend skeleton can be run locally without Docker with:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run backend tests:

```bash
pytest
```

Run Alembic commands from the host with PostgreSQL running:

```bash
export DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops
alembic current
alembic upgrade head
alembic check
```

When running inside Docker Compose, the backend uses the `postgres` service hostname from `DATABASE_URL`.

Run PostgreSQL-backed RLS tests with local Postgres:

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest tests/test_rls_postgres.py -q
```

PostgreSQL is required for true RLS verification. SQLite-based tests can validate helper behavior and migration compatibility, but they do not enforce PostgreSQL Row-Level Security policies.

RLS runtime context is set transaction-locally before scoped reads using:

```txt
app.current_user_id
app.current_role
app.current_scope_type
app.current_scope_keys
app.has_global_scope
```

For V1 IT Operations RLS, `app.current_scope_keys` contains comma-separated department UUID strings from assigned department access scopes. Human-readable `access_scopes.scope_key` values such as `finance` remain product metadata; domain table RLS compares against `department_id` UUIDs. Missing RLS context fails closed at the policy layer unless `app.has_global_scope` is true.

### Query Engine Backend

Milestone 4 implemented the backend Query Engine foundation, and Milestone 5 PR1 closed the remaining backend compliance gaps needed before Ask Data UI work can begin. The backend includes:

* Domain Pack Loader in `backend/app/query_engine/domain_pack_loader.py`
* IT Operations domain pack files under `backend/app/domains/it_operations/domain_pack/`
* Query Templates API
* `LLMProvider` interface and deterministic `MockLLMProvider`
* SQL generator wrapper
* Schema Context Builder
* read-only SQL Validator
* dedicated read-only PostgreSQL runtime role hardening
* scoped SQL Executor that uses PostgreSQL RLS
* internal Query Engine orchestration service
* Query Run API and `QueryRun` persistence
* query clarification endpoint
* own-history and scope-aware query history endpoints
* `department-history` V1 compatibility alias
* deterministic self-correction for safe validation failures
* hardened safe query metadata for future Ask Data UI technical states
* PostgreSQL/RLS-backed query tests and security regression tests

The Domain Pack Loader loads the local IT Operations schema, business terms, and approved query templates. It is the source for safe schema context and deterministic template-backed SQL generation. `MockLLMProvider` maps known domain-pack questions to structured SQL generation results and returns safe clarification for unsupported questions. No real LLM provider, network call, API key, OpenAI, Groq, or Anthropic integration is required.

Query Templates API:

```txt
GET /api/v1/query-templates
GET /api/v1/query-templates/{id}
```

Query Run API:

```txt
POST /api/v1/queries/run
POST /api/v1/queries/{query_run_id}/clarify
GET /api/v1/queries/history
GET /api/v1/queries/scope-history
GET /api/v1/queries/department-history
GET /api/v1/queries/{query_run_id}
```

SQL visibility is permission-controlled:

* Manager responses do not include `generated_sql` or `executed_sql`.
* Analyst and Admin responses include SQL only through `can_view_sql`.
* SQL visibility is an API response rule; `QueryRun` may store generated and executed SQL internally for auditability and testing.

RLS runtime model:

* The local `queryops` role owns tables, so PostgreSQL table-owner RLS bypass is relevant.
* Query execution switches transaction-locally to the dedicated non-owner read-only role `queryops_query_runtime`.
* The runtime role has SELECT-only grants for allowed queryable tables and cannot access non-queryable `it_audit_events`.
* Query execution uses validator `sanitized_sql`, transaction-local RLS context, PostgreSQL RLS, read-only transaction mode, statement timeout, and row caps.

Current Query Engine limitations:

* User-supplied template parameters are not supported through the public API.
* Raw SQL input is not supported.
* Real LLM providers are not implemented.
* Query detail endpoints return only the authenticated user's own runs.
* Scope-aware query history requires assigned access scopes and the appropriate history permission.
* Full domain pack expansion to 36 templates / 40 evaluation cases is not implemented.
* Scheduled card refresh, actions, approvals, and notifications are not implemented.

### CSV Export and Dashboard Card Refresh

Milestone 6 PR3 added controlled CSV export for successful owned query runs and visible dashboard cards:

```txt
POST /api/v1/query-runs/{query_run_id}/export-csv
POST /api/v1/cards/{card_id}/export-csv
```

Both endpoints require authentication, valid CSRF, and `can_export_results`, which is seeded for Analyst and Admin. Analysts may export only when every referenced `DataResource` is queryable and exportable. Admin also receives `can_export_restricted_results`, allowing export when every referenced resource is queryable but one or more is normally non-exportable. Resources marked `is_queryable=false` and missing resources remain blocked for every role.

Admin restricted exports do not bypass the normal export boundary. Stored SQL is revalidated and re-executed through the read-only `queryops_query_runtime` role under the current viewer's RLS context with row limits and CSV injection protection. Every successful export is audited; restricted Admin exports record the override permission and safe restricted table names without SQL or raw rows.

The optional `filename` must be printable ASCII, may omit the `.csv` extension, and may produce a final filename of at most 255 characters. `include_headers` defaults to `true` and must be a boolean.

Milestone 6 PR4 added authorized browser downloads for both export endpoints. Ask Data exposes Export CSV only for successful exportable query runs and dashboard cards expose Export CSV only when the current user has `can_export_results`. The frontend never builds CSV from visible rows; it downloads the backend response so SQL validation, current-viewer RLS, sanitization, export policy, and audit remain authoritative.

PR4 also added current-viewer card refresh:

```txt
POST /api/v1/cards/{card_id}/refresh
```

Refresh requires authentication and CSRF, checks dashboard visibility, locates the latest successful linked query run, validates stored executed SQL again, verifies trusted referenced-table metadata, and executes only validator-sanitized SQL through `queryops_query_runtime` in a read-only transaction with transaction-local RLS. The preview returns at most 100 rows and never returns SQL or runtime details. Each successful refresh creates a linked `QueryRun` owned by the current viewer without persisting raw rows. Personal dashboard cards refresh once when loaded and can be refreshed manually; a failed manual refresh keeps the previous in-memory result visible.

Run Query Engine unit/API tests:

```bash
cd backend
.venv/bin/pytest \
  tests/test_domain_pack_loader.py \
  tests/test_query_templates_api.py \
  tests/test_llm_provider.py \
  tests/test_sql_generator.py \
  tests/test_schema_context.py \
  tests/test_sql_validator.py \
  tests/test_query_engine_service.py \
  tests/test_query_api.py \
  tests/test_query_engine_security_regression.py \
  tests/test_query_evaluation_set.py -q
```

Run PostgreSQL query/RLS tests:

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest \
  tests/test_rls_postgres.py \
  tests/test_query_runtime_role_postgres.py \
  tests/test_sql_executor_postgres.py \
  tests/test_query_engine_postgres.py \
  tests/test_query_api_postgres.py \
  tests/test_query_engine_security_postgres.py -q -rs
```

Safe local API smoke examples:

```bash
# Login as a manager. Save cookies and copy csrf_token from the JSON response.
curl -i -c /tmp/queryops-cookies.txt \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8000/api/v1/demo/login \
  -d '{"email":"demo.manager@queryops.local"}'

# Use the csrf_token from login for POST requests.
export CSRF_TOKEN="paste-csrf-token-here"

curl -b /tmp/queryops-cookies.txt \
  http://localhost:8000/api/v1/query-templates

curl -b /tmp/queryops-cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -X POST http://localhost:8000/api/v1/queries/run \
  -d '{"question":"How many open support tickets exist in my department by priority?","template_id":"open_support_tickets_by_department"}'

curl -b /tmp/queryops-cookies.txt \
  http://localhost:8000/api/v1/queries/history

curl -b /tmp/queryops-cookies.txt \
  http://localhost:8000/api/v1/queries/{query_run_id}
```

The manager example intentionally does not return raw SQL. Use an Analyst or Admin demo session to verify SQL visibility through `can_view_sql`.

Seed deterministic development data after migrations have been applied:

```bash
docker compose up -d postgres
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_it_operations.py --profile small --reset
.venv/bin/python scripts/seed_it_operations.py --profile medium --reset
```

The seed script is development-only and deterministic. Supported profiles are `small` for fast local or CI-style checks and `medium` for demo-scale local data. The `--reset` flag deletes seeded rows from the product and IT Operations tables before reseeding; it does not drop tables or modify Alembic migration state.

After updating an existing development database to the final Milestone 6 export policy, rerun the seed command with the current profile and `--reset`. Existing rows are not updated in place, so the reset is required to install `can_export_results`, Admin-only `can_export_restricted_results`, and the current `DataResource.is_exportable` policy.

Local demo auth uses seeded users through `POST /api/v1/demo/login`, then hydrates the current user with `GET /api/v1/auth/me`. Login sets a signed, expiring httpOnly `qo_session` cookie and a readable `qo_csrf` cookie; state-changing authenticated requests such as `POST /api/v1/auth/logout` must send `X-CSRF-Token`.

### Frontend

The frontend skeleton can be run locally without Docker with:

```bash
cd frontend
npm install
npm run dev
```

Build and test commands:

```bash
npm run build
npm test
```

The frontend auth client calls the backend at `http://localhost:8000` by default.
Override it with `VITE_API_BASE_URL` if needed.

## Verification

### Backend

```bash
cd backend
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

Run the PostgreSQL RLS subset:

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest tests/test_rls_postgres.py -q
```

Run the full backend suite with PostgreSQL-specific Query Engine tests enabled:

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest tests/test_exports_postgres.py -q -rs
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest tests/test_card_refresh_postgres.py -q -rs
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest
```

### Frontend

```bash
cd frontend
npm install
npm test
npm run build
```

### Docker Compose

With Docker Desktop or another Docker daemon running:

```bash
cp .env.example .env
docker compose config
docker compose up --build
```

## Environment Variables

A `.env.example` file should document all required environment variables.

Example planned variables:

```env
AUTH_MODE=demo
SESSION_SECRET_KEY=queryops-local-session-secret
SESSION_COOKIE_SECURE=false
SESSION_MAX_AGE_SECONDS=28800
POSTGRES_DB=queryops
POSTGRES_USER=queryops
POSTGRES_PASSWORD=queryops
POSTGRES_PORT=5432
BACKEND_PORT=8000
FRONTEND_PORT=5173
DATABASE_URL=postgresql+psycopg://queryops:queryops@postgres:5432/queryops
VITE_API_BASE_URL=http://localhost:8000
```

Real secrets must never be committed to Git.

## Project Goals

QueryOps AI is intended to be a portfolio-grade software project that demonstrates:

* practical AI product design
* backend architecture
* database modeling
* permission-aware data access
* secure SQL execution
* action approval workflows
* auditability
* synthetic data generation
* evaluation methodology
* clean frontend dashboards
* Docker-based local development
* strong documentation and incremental delivery

## Current Status

Milestones 0 through 6 are complete and merged into `main`; PR #24 merged M6 PR5 Card Reordering & Layout Persistence and the final Admin restricted-export policy. Milestone 7 — Product UX & Dashboard Redesign is active. M7 PR1 is implementation-complete on `feature/m7-product-shell-navigation`; it establishes the routed dark-first product shell, focused navigation, Profile, and transitional My Dashboard experience.

The Milestone 7 UX direction is dark-first with a persistent light option, responsive navigation, My Dashboard as the authenticated home, permission-aware routes, and Scope terminology in the general product UI. Milestone 7 remains incomplete: role-aware Home metrics and the dashboard browser are planned for PR2, the dashboard editor/grid/visualizations for PR3, and the Ask Data redesign for PR4. M7 PR2 is not active and has not started.

Implemented foundation functionality includes:

* FastAPI backend skeleton with `GET /health`
* React + TypeScript + Vite frontend shell with backend health check
* Docker Compose setup for PostgreSQL, backend, and frontend
* `.env.example` with safe local placeholders
* basic backend and frontend tests
* initial GitHub Actions CI workflow
* SQLAlchemy and Alembic database foundation
* product and IT Operations domain schema
* deterministic IT Operations seed profiles and seed tests
* local demo auth session endpoints with CSRF protection and session expiration
* role and permission mapping with role upgrade request flow
* Access Context Foundation with access scopes, data resources, and simple access decisions
* scope-aware PostgreSQL RLS policies for department-scoped IT Operations domain tables
* RLS context helper and initial security/RLS test suite
* backend Query Engine foundation with domain packs, templates, mock generation, schema context, SQL validation, scoped read-only execution, Query Run API, `QueryRun` persistence, and security regression tests
* Ask Data frontend with role-gated SQL and diagnostics
* dashboard catalog, personal dashboards, and saved dashboard cards
* controlled query-run and dashboard-card CSV export with permissions, exportability policy, current-viewer RLS execution, CSV injection protection, and successful export audit persistence
* authorized Ask Data and dashboard-card CSV download controls
* automatic/manual dashboard-card refresh under current-viewer RLS with safe table previews and viewer-owned refresh history

Current milestone status:

```txt
Milestone 6 — Dashboards, Cards & CSV Export is complete.
Milestone 7 — Product UX & Dashboard Redesign is active.
M7 PR1 — Product Shell, Routing & Navigation is implementation-complete on feature/m7-product-shell-navigation.
```

PR5 persists the order of cards in owned personal dashboards through `DashboardCard.position`. It includes accessible drag-and-drop and Move Up / Move Down controls, but does not add card resizing, x/y grid coordinates, width/height persistence, advanced `layout` behavior, scheduled refresh, dashboard starring/cloning, actions, approvals, notifications, real external LLM calls, Supabase Auth, Redis/background jobs, or domain expansion. Those deferred areas remain outside Milestone 6.

## License

No license has been selected yet.
