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

M8 PR4 completes the two V1 backend actions, `reclaim_unused_license` and `disable_inactive_user`, through the shared action lifecycle:

```txt
POST /api/v1/actions/preview
POST /api/v1/actions/request
GET  /api/v1/actions
GET  /api/v1/actions/{action_request_id}
POST /api/v1/actions/{action_request_id}/cancel
GET  /api/v1/approvals/pending
POST /api/v1/approvals/{approval_id}/approve
POST /api/v1/approvals/{approval_id}/reject
```

The backend deterministically reads current operational data through `queryops_query_runtime`, a read-only transaction, transaction-local RLS context, and PostgreSQL RLS. Draft previews expire after 30 minutes and submitted approvals after 24 hours. Approval synchronously revalidates current rows and dependencies before entering the narrow write role. License reclaim uses current assignment policy; inactive-user disablement requires an active human with no successful login for at least 90 days. Service accounts are always skipped. Privileged humans, humans with open critical security events, and cross-scope humans require Admin override; more than 20 actionable records is a request-level Admin rule.

Successful execution atomically persists the domain mutation, application lifecycle audit, one domain audit per changed record, lifecycle state, and database-only notifications. Failure rolls back all success-side effects and uses a separate safe failure transaction. M8 PR5 adds requester UX for deterministic current-result suggestions, safe previews, submission, owned action tracking/detail, persisted timelines, and pending cancellation. M8 PR6 adds permission-aware Approvals and Audit workspaces, synchronous decision UX, current-recipient notification access, and exact activity totals without changing those backend guarantees. M8 PR7 adds isolated release-blocking browser coverage, a tracked security matrix, and explicit no-skip PostgreSQL CI gates. Milestone 8 is complete; the next milestone has not started.

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

PostgreSQL is included for the local development environment. Milestones 0 through 7 are complete and merged into `main` through PR #28. M8 PR1 through PR5 are merged through PR #33, M8 PR6 is merged through PR #34, and M8 PR7 is implementation- and verification-complete on `feature/m8-e2e-security-completion` but is not merged. Milestone 8 is complete. The current backend includes both V1 actions, approvals, synchronous execution, action/domain audit, database notification APIs, safe timelines, deterministic template suggestions, requester-owned action lists, and exact authorized activity totals. The frontend includes requester Actions, Approvals, Audit, and database Notifications UX.

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

### Isolated M8 E2E preparation

The state-changing M8 workflow must never use the normal development database. Use a fresh PostgreSQL cluster with no volume, create a separately named E2E database, and keep the normal database URL only as the safety comparator:

```bash
docker run --rm -d --name queryops-m8-e2e \
  -e POSTGRES_DB=queryops -e POSTGRES_USER=queryops -e POSTGRES_PASSWORD=queryops \
  -p 55433:5432 postgres:16-alpine
docker exec queryops-m8-e2e createdb -U queryops queryops_e2e_test

cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:55433/queryops_e2e_test \
  .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:55433/queryops_e2e_test \
  .venv/bin/python scripts/seed_it_operations.py --profile small --reset
M8_E2E_DATABASE_DISPOSABLE=1 \
M8_E2E_DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:55433/queryops_e2e_test \
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:55433/queryops \
POSTGRES_DB=queryops \
  .venv/bin/python scripts/prepare_m8_e2e.py
```

The preparation script is PostgreSQL-only and idempotent. It rejects missing opt-in, non-loopback endpoints, database names without a test/dev/e2e marker, the configured normal application database, ambiguous URLs, and endpoint query overrides. Run the backend with `DATABASE_URL` pointed at `queryops_e2e_test`, run `frontend/e2e/m8-workflow.spec.ts` once with retries disabled, then run `docker stop queryops-m8-e2e` so Docker removes the container. The general E2E suite excludes `@m8-primary`; CI owns a separate fresh database for the state-changing workflow.

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

Action approval runtime model:

* `reclaim_unused_license` and `disable_inactive_user` approvals revalidate current rows and execute synchronously through the non-owner `queryops_action_runtime` role.
* The action role is `NOLOGIN`, `NOINHERIT`, `NOSUPERUSER`, and `NOBYPASSRLS`, and is granted to the explicit application login role from `QUERYOPS_APP_DATABASE_ROLE` with inheritance disabled and SET enabled; action code must use `SET LOCAL ROLE`.
* Its grants are limited to required reads, three `license_assignments` UPDATE columns, `directory_users.account_status`/`updated_at` UPDATE, and scoped `it_audit_events` INSERT. Role-scoped PostgreSQL policies bind mutations to the active scope and allow only active human users to become disabled.
* Approval, mutation, application/domain audit, and database notifications commit atomically. Failure state is recorded separately after a rollback.
* Backend APIs provide pending approval review/decisions, current-recipient notification reads, and permission-scoped audit reads. Requester Actions UX is merged; PR6 is the active human-facing approval, audit, and notification integration.

Current Query Engine limitations:

* User-supplied template parameters are not supported through the public API.
* Raw SQL input is not supported.
* Real LLM providers are not implemented.
* Query detail endpoints return only the authenticated user's own runs.
* Scope-aware query history requires assigned access scopes and the appropriate history permission.
* Full domain pack expansion to 36 templates / 40 evaluation cases is not implemented.
* Scheduled card refresh, scheduled/background actions, and external notification delivery are not implemented. Approval, audit, and notification frontend screens are limited to the active PR6 scope.

### Role-Aware Home and Dashboard Browser

M7 PR2 adds these authenticated read endpoints:

```txt
GET /api/v1/home/overview
GET /api/v1/dashboards/library
GET /api/v1/dashboards/{dashboard_id}
```

Home always returns the current app user's personal product summary. User receives no operational domain metrics. Manager and Analyst receive aggregate-only operational metrics across their authorized scopes. Admin receives global operational aggregates and independently permission-gated product administration counts. Operational reads use existing `DataResource` authorization, `queryops_query_runtime`, a read-only transaction, transaction-local `UserAccessContext` RLS settings, and PostgreSQL RLS. QueryOps app users are never matched to IT Operations directory users by email, name, provider identity, or any other inferred identity.

My Dashboard at `/` includes an Owned/Shared library with title/description search, All/Owned/Shared filters, Recently updated/Name/Created sorting, compact personal dashboard creation, and an accessible metadata-only preview dialog. Preview never refreshes cards or fetches results. `Open dashboard` navigates to `/dashboards/:dashboardId`, where existing current-viewer refresh and permission-gated CSV export remain available. Owned personal dashboards retain explicit arrange-only M6 ordering compatibility.

Home and the new dashboard read APIs do not return SQL, raw operational rows, raw card config, raw card layout, owner email, or sensitive event detail. PR2 does not add charts, card resizing, an editor, Add Card, context menus, or an Ask Data redesign; those areas remain deferred.

### Dashboard Editor and Visualizations

M7 PR3 upgrades `/dashboards/:dashboardId` while keeping View mode as the default. Authorized owners can enter Edit mode, draft layout changes locally, save with optimistic `layout_version` concurrency, or cancel without persisting. Desktop and tablet use constrained 12-column and 6-column grids with drag and approved resize presets; mobile uses a single column with explicit Move Up, Move Down, and size presets instead of free drag-resize.

Approved presets provide compact, standard, and tall card sizes: Tables can use 2/3/4 grid-row heights, Cartesian charts add compact and large layouts, and overflowing Table or Status list content scrolls inside the card without resizing the dashboard automatically.

Dashboard cards support KPI, Table, Bar, Line, Area, Donut, Semicircle gauge, Stacked bar, and Status list presentations. QueryOps recommends a compatible visualization from the current in-memory refresh result. A saved manual override remains authoritative, `Reset to recommended` restores automatic selection, and incompatible manual choices render a safe Table fallback without deleting the preference. Refreshed rows are never persisted in card config, layout, local storage, or URL state.

The full dashboard route provides accessible right-click, ellipsis, and keyboard card menus for authorized refresh, CSV export, source view, rename, visualization changes, resize presets, duplicate, and remove actions. Dashboard owners can rename, create a personal duplicate, or soft-archive the dashboard. Source view is gated by effective `can_view_sql` and returns only the original question and stored sanitized/executed SQL. Card removal preserves its `SavedQuery` and all `QueryRun` history.

Edit mode can add cards from approved templates or eligible recent successful query results. Both flows continue through the existing Query Engine, Save as Card, current-viewer refresh, SQL validation, read-only runtime, PostgreSQL RLS, and export/audit boundaries. PR3 does not add cross-dashboard card movement, shared-dashboard personalization, department/global creation, Ask Data redesign, or Milestone 8 features.

### Ask Data Redesign and Final UX Hardening

M7 PR4 keeps Ask Data at `/ask` and replaces the previous multi-panel workspace with a command-first hierarchy: question composer, stable current result, and collapsed progressive details. Users without free-query permission select an approved template; permitted roles can ask free questions or edit a selected template question, which safely clears the template association.

Templates and the five most recent own query requests open in accessible drawers that become full-screen sheets on mobile. Quick history always requests `limit=5`, `offset=0`, and `include_sql=false`; it reruns a new governed query and never restores historic rows or exposes SQL. Current results reuse the PR3 visualization recommendation and renderer for an in-memory Visual/Table switch with Table as the safe fallback.

Successful results expose one compact Save to Dashboard / Export CSV toolbar. Save targets personal dashboards, reuses the existing QueryRun-to-card endpoint, and applies only a sanitized recommended visualization—never result rows. Export continues through the backend CSV endpoint and its current-viewer RLS, validation, sanitization, policy, and audit controls. SQL and Diagnostics are absent from the DOM without effective `can_view_sql`.

The shared overlay system traps focus, restores it predictably, locks background scrolling, supports Escape and backdrop dismissal, and remains full-width on small screens. The dashboard editor's dedicated handle supports pointer and arrow-key movement without turning adjacent controls into drag targets. Focused Chromium Playwright coverage exercises User, Analyst, and Admin flows, responsive drawers, restricted export behavior, save/open-dashboard behavior, and persisted handle movement.

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
npx playwright install chromium
npm run test:e2e
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

Run the full backend suite with PostgreSQL-specific tests against a separate disposable database. Action tests refuse the configured application database and require an explicit destructive-test opt-in:

```bash
docker compose up -d postgres
docker compose exec postgres dropdb --if-exists -U queryops queryops_test
docker compose exec postgres createdb -U queryops queryops_test
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops_test .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops_test .venv/bin/alembic check
POSTGRES_TEST_DATABASE_DISPOSABLE=1 \
POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops_test \
  .venv/bin/pytest
```

Never point `POSTGRES_TEST_DATABASE_URL` at the normal `POSTGRES_DB`. The action PostgreSQL fixtures run Alembic and reset deterministic seed data.

### Frontend

```bash
cd frontend
npm install
npm test
npm run build
npx playwright install chromium
npm run test:e2e
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
QUERYOPS_APP_DATABASE_ROLE=queryops
POSTGRES_TEST_DATABASE_DISPOSABLE=0
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

Milestones 0 through 7 are complete and merged into `main`; M7 PR4 merged through PR #28. Milestone 8 — Actions, Approvals & Audit is complete. M8 PR1 through PR5 are merged through PR #33, M8 PR6 is merged through PR #34, and M8 PR7 is implementation- and verification-complete on `feature/m8-e2e-security-completion` but is not merged. The next milestone has not started.

The completed Milestone 7 experience is dark-first with a persistent light option, responsive navigation, My Dashboard as the authenticated home, permission-aware routes, Scope terminology, a responsive dashboard editor, safe visualizations, and command-first Ask Data. The completed Milestone 8 experience adds the two governed V1 actions, requester Actions, exact-scope/global Approvals, scoped/global Audit, database Notifications, synchronous execution, and release-blocking PostgreSQL/browser evidence.

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
* role-aware Home personal/scoped/global aggregate summaries without app-user/directory-user identity inference
* Owned/Shared dashboard search, filters, sorting, accessible safe preview, and `/dashboards/:dashboardId`
* full dashboard presentation with preserved secure refresh/export and explicit owned-personal arrange compatibility
* explicit capability-gated dashboard View/Edit modes with optimistic layout concurrency
* responsive 12/6/1 grid layouts with constrained desktop/tablet resize and mobile presets
* nine safe visualization types with deterministic recommendation, manual override, and accessible fallback behavior
* authorized dashboard/card context menus, mutations, SQL source view, and Add Card sources
* command-first Ask Data with accessible template and five-item own-history drawers
* PR3-powered in-memory Visual/Table result switching and progressive technical details
* consolidated governed result save/export controls and clarification-safe state handling
* requester Actions UX with deterministic current-template recommendations, safe preview/submission, owned tracking/detail, timelines, and cancellation
* permission-aware Approvals and Audit workspaces, synchronous decision UX, exact activity badges, and current-recipient database notification controls
* deterministic Chromium Playwright coverage in CI

Current milestone status:

```txt
Milestone 6 — Dashboards, Cards & CSV Export is complete.
Milestone 7 — Product UX & Dashboard Redesign is complete.
M7 PR1 — Product Shell, Routing & Navigation is complete and merged through PR #25.
M7 PR2 — Role-Aware Home & Dashboard Browser is complete and merged through PR #26.
M7 PR3 — Dashboard Editor, Grid & Visualizations is complete and merged through PR #27.
M7 PR4 — Ask Data Redesign & Final UX Hardening is complete and merged through PR #28.
M8 PR1 through PR4 are complete and merged through PR #32.
M8 PR5 — Requester Actions UX is complete and merged through PR #33.
M8 PR6 — Approvals, Audit & Notifications UX is complete and merged through PR #34.
M8 PR7 — E2E, Security Hardening & Completion is implementation- and verification-complete but not merged.
Milestone 8 — Actions, Approvals & Audit is complete; the next milestone has not started.
```

PR6 keeps backend authorization authoritative while adding exact approval/notification activity badges, permission-aware Approvals and Audit workspaces, synchronous approve/reject dialogs, safe related navigation, and current-recipient database notification controls. Under the current permission catalog, Analyst receives exact-scope approval and Audit UX, Admin receives global/override/self-approval UX, Manager retains requester Actions and notifications without Audit access, and User receives notifications without Actions, Approvals, or Audit navigation. The private planning description of a future limited Manager audit view is not implemented because the backend does not currently grant that permission.

PR7 verification passed 14 guarded-database tests, the exact 20-case action-security suite plus two concurrency cases, 756 default backend tests with 151 expected PostgreSQL-only skips, all 907 disposable-PostgreSQL tests with no skips, 247 frontend tests, TypeScript, the production build, seven general Chromium flows, two isolated primary/negative M8 flows, and a fresh Alembic upgrade/current/no-diff check through migration 0010. The tracked release matrix maps all exact 20 and broader 30 security cases. The final **Manual M8 PR7 release review — not a CodeRabbit result** found and fixed 4 Minor issues with no Critical or Major finding and no unresolved actionable issue.

PR7 changed no schema, migration, normal seed, permission, role mapping, RLS, action policy, lifecycle, execution, audit writer, notification recipient, or public API contract. M8 intentionally remains limited to `reclaim_unused_license` and `disable_inactive_user`, synchronous execution, and database-only notifications. It has no automatic retry or rollback action, queue, worker, scheduler, Redis, WebSocket, or external delivery. Operational intervention is still required if both execution and separate failure persistence fail.

PR5 persists the order of cards in owned personal dashboards through `DashboardCard.position`. It includes accessible drag-and-drop and Move Up / Move Down controls, but does not add card resizing, x/y grid coordinates, width/height persistence, advanced `layout` behavior, scheduled refresh, dashboard starring/cloning, actions, approvals, notifications, real external LLM calls, Supabase Auth, Redis/background jobs, or domain expansion. Those deferred areas remain outside Milestone 6.

## License

No license has been selected yet.
