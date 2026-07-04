# QueryOps AI — Agent Instructions

These instructions apply to all AI coding agents working in this repository.

## 1. Read Before Coding

Before making code changes, always read:

1. `README.md`
2. `PROJECT_PLAN.md`
3. `AGENTS.md`
4. Local planning documents under `docs/planning/`, if available

The `docs/planning/` directory is intentionally ignored by Git. It may exist only in the local workspace and should be used as private implementation context when available.

Do not commit files from `docs/planning/`. Do not modify files under `docs/planning/` unless explicitly asked.

## 2. Milestone Source of Truth

The current development status and any active target are defined in `PROJECT_PLAN.md`.

```txt
Agents must follow PROJECT_PLAN.md and must not implement future milestone work unless explicitly requested.
```

If no milestone is active, do not infer the next milestone. If a task is outside the current approved scope in `PROJECT_PLAN.md`, stop and report the mismatch instead of implementing it.

## 3. Scope Control

Agents must:

* implement only the requested milestone or task
* keep changes small and reviewable
* avoid unplanned scope
* avoid future-proof abstractions before they are needed
* update README only when setup commands, behavior, or verification commands actually change
* preserve existing user changes
* avoid unrelated refactors

If implementation details are unclear:

1. Check `PROJECT_PLAN.md`
2. Check local `docs/planning/`
3. Choose the smallest implementation that satisfies the active milestone
4. Ask for clarification only when the ambiguity cannot be resolved from local context

## 4. Permanent Guardrails

Do not commit secrets.

Do not commit generated build artifacts.

Do not commit local environment files.

Do not commit ignored private planning documents.

Do not introduce real LLM calls before requested.

Do not silently change product scope.

Do not rewrite unrelated files.

Prefer boring, maintainable structure over clever abstractions.

## 5. Current Milestone Notes

The milestone status is defined in `PROJECT_PLAN.md`.

At the time this file was updated, the latest completed target is:

```txt
Milestone 6 PR1 — Dashboards/Cards Backend Foundation
```

Milestone 0, Milestone 1, Milestone 2, Milestone 2.5, Post-Milestone 2.5 hardening, Milestone 3, Milestone 4, and Milestone 5 are complete under the previous scopes. Milestone 5 PR6 has been merged into `main`. M5 Ask Data and the M5 frontend redesign are complete.

Milestone 6 is active. `M6 PR1 — Dashboards/Cards Backend Foundation` is complete and merged into `main`. `M6 PR2 — Dashboard/Card UI` is active on branch `feature/m6-dashboard-ui`.

Milestone 2.5 introduced `access_scopes`, `user_access_scopes`, `data_resources`, `UserAccessContext`, `AccessDecision`, and `evaluate_access(subject, action, resource, context)`.

Milestone 3 added the security foundation for scope-aware PostgreSQL RLS before Query Engine work begins.

Milestone 3 delivered scope-aware PostgreSQL RLS, a `SET LOCAL` RLS context helper, DB session/helper integration for future Query Engine use, initial security/RLS tests, and policy helper refinements.

Milestone 4 implemented the backend Query Engine foundation on top of the existing Access Context Foundation and PostgreSQL RLS behavior.

Milestone 5 PR1 closed the remaining Milestone 4 backend Query Engine compliance gaps before frontend Ask Data UI began. That PR implemented:

* `POST /api/v1/queries/{query_run_id}/clarify`
* `GET /api/v1/queries/scope-history`
* `GET /api/v1/queries/department-history` as a V1 compatibility alias
* deterministic self-correction
* hardened safe query metadata for the future Ask Data UI

Milestone 5 PR5 added Ask Data role-gated SQL and Diagnostics tabs. Analyst/Admin can view generated/executed SQL in the SQL tab and safe technical diagnostics in the Diagnostics tab. User/Manager cannot view SQL tabs, Diagnostics tabs, generated SQL, executed SQL, or technical diagnostics. PR5 also added final Ask Data role matrix tests for User, Manager, Analyst, and Admin.

Milestone 5 PR6 added the Tailwind UI foundation, class-based light/dark mode, redesigned app shell/sidebar, redesigned Dashboard, focused Ask Data command workspace, light polish for remaining frontend pages, and final CSS/docs cleanup. PR6 did not change backend behavior, query execution behavior, auth/roles/RLS, dashboard card persistence behavior, CSV export behavior, action preview behavior, approvals, notifications, real LLM providers, API keys, Supabase Auth, Redis/background jobs, domain pack expansion, UI component libraries, or charting libraries.

Milestone 6 PR1 includes the dashboard catalog backend endpoint, my dashboard backend endpoint, dashboard creation backend endpoint, saving successful owned query runs as dashboard cards, safe metadata-only serializers, auth, CSRF, strict payload validation, dashboard visibility/manageability checks, and backend tests. It uses existing backend auth, CSRF, permission, and response conventions. Responses are metadata-only, do not execute saved cards, and do not expose SQL beyond existing `can_view_sql` API rules.

Milestone 6 PR2 Checkpoint 1 frontend dashboard/card API clients and types is complete. Checkpoint 2 read-only My Dashboard loading is complete. The current PR2 checkpoint adds personal dashboard creation from the Dashboard page: it may submit `POST /api/v1/dashboards` with `visibility_scope: "personal"`, show permission guardrails, refresh `GET /api/v1/dashboards/my`, and add frontend tests for validation, CSRF-backed request behavior, refetching, role coverage, and SQL non-exposure.

Milestone 4 delivered:

* Domain Pack Loader
* Query Templates API
* `LLMProvider` interface
* `MockLLMProvider`
* SQL generator wrapper
* Schema Context Builder
* SQL validator
* runtime RLS role hardening
* scoped read-only Query Executor
* internal Query Engine orchestration service
* Query Run API
* `QueryRun` persistence
* PostgreSQL/RLS query tests
* Query Engine security regression and deterministic MockLLM evaluation tests

Query Engine security rules:

* Backend authorization is the source of truth; frontend visibility is never enough.
* Query execution is read-only.
* SQL must be validated before execution.
* Execute only validator `sanitized_sql`, never raw user or provider output.
* Execution must use the dedicated non-owner read-only role `queryops_query_runtime`.
* Execution must use transaction-local PostgreSQL RLS context and PostgreSQL RLS.
* Non-queryable `DataResource` records are denied.
* `it_audit_events` is intentionally non-queryable in V1.
* Query Engine code must continue to use `UserAccessContext`, `DataResource`, `AccessDecision`, `evaluate_access(...)`, `authorize_resource_access(...)`, `RLSContext`, `build_rls_context(...)`, `set_rls_context(...)`, PostgreSQL RLS policies from `0005_scope_aware_rls.py`, and the existing `QueryRun` model.
* No real LLM calls, external provider integrations, or API-key requirements are allowed in Milestone 4.

Out of scope for the current M6 PR2 checkpoint unless explicitly requested:

* Dashboard Catalog UI
* department/global dashboard creation UI
* Save as Card modal
* Ask Data save-card integration
* drag-and-drop UI
* CSV export
* card refresh execution
* actions
* approvals
* notifications
* real LLM/API-key support
* Supabase Auth
* domain pack expansion
* Full ABAC
* ReBAC
* masking
* policy builder UI
* dynamic policy engine
* tenant/project/region governance
* background jobs
* Redis
* API rate limiter

Later Milestone 6 PRs may handle dashboard catalog/create flows, Save as Card integration, card refresh, reordering, and CSV export. Later milestones will handle actions, approvals, notifications, real LLM/API-key support, and Supabase Auth unless explicitly requested. Do not add card refresh execution, dashboard catalog/create behavior, Save as Card integration, action execution, approval behavior, CSV export, real LLM providers, API keys, Supabase Auth, or new Ask Data behavior outside the active approved PR scope.

## 6. Product Direction

QueryOps AI is a governed conversational data workspace.

The product should eventually support:

* natural-language questions over structured data
* safe SQL generation
* SQL validation
* scoped database execution
* explained results
* saved cards and dashboards
* controlled operational actions
* approval workflows
* audit logs

The first domain is IT Operations, but the core system must remain generic.

IT Operations is a domain pack, not the whole product.

## 7. Architecture Decisions

Follow these locked decisions unless explicitly changed by the user:

* monorepo
* React + TypeScript + Vite frontend
* FastAPI + Python backend
* PostgreSQL database
* SQLAlchemy 2 and Alembic for database work
* Docker Compose for local development
* demo auth before real Supabase Auth
* Supabase Auth planned later for identity only
* QueryOps manages its own roles, departments, and permissions
* PostgreSQL RLS required in a later milestone
* LLM provider abstraction
* no direct LLM database mutations
* actions must be executed by deterministic backend logic
* actions require preview, policy check, approval, execution, and audit

## 8. Documentation Rules

Update `README.md` when:

* setup commands change
* Docker commands change
* backend run commands change
* frontend run commands change
* environment variables change
* repository structure changes
* verification commands change

Update `PROJECT_PLAN.md` only when the development plan or active milestone changes.

Keep `README.md` focused on the project.

Keep `PROJECT_PLAN.md` focused on implementation control.

Keep `AGENTS.md` focused on agent behavior rules.

## 9. Testing Rules

When adding backend code, add or update backend tests when practical.

When adding frontend code, add or update frontend tests when practical.

When adding database schema or seed behavior, add or update migration, seed, and relationship tests when practical.

Security-related behavior in later milestones must have tests.

Do not add complex E2E tests before the supporting app behavior exists.

Current verification commands:

Default backend suite:

```bash
cd backend
.venv/bin/pytest
```

PostgreSQL/RLS/Query Engine suite:

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest tests/test_rls_postgres.py -q -rs
```

Alembic with local PostgreSQL:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

## 10. Git Rules

Before starting work:

```bash
git status
```

Before finishing work:

```bash
git status
```

Only stage files related to the current task.

Do not stage ignored planning files.

## 11. Local Planning Files

Expected local planning files, if present:

```txt
docs/planning/01-product-brief.md
docs/planning/02-mvp-prd.md
docs/planning/03-technical-architecture.md
docs/planning/04-it-operations-domain-pack.md
docs/planning/05-security-permissions-matrix.md
docs/planning/06-actions-approvals-audit.md
docs/planning/07-api-contract.md
docs/planning/08-ui-flows-wireframes.md
docs/planning/09-evaluation-testing-plan.md
docs/planning/10-development-milestones.md
```

Use these files as context, but do not copy large private sections into committed files.
