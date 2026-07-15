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

At the time this file was updated, the latest checkpoint-complete target is:

```txt
M7 PR3 — Dashboard Editor, Grid & Visualizations
```

Milestone 0, Milestone 1, Milestone 2, Milestone 2.5, Post-Milestone 2.5 hardening, Milestone 3, Milestone 4, and Milestone 5 are complete under the previous scopes. Milestone 5 PR6 has been merged into `main`. M5 Ask Data and the M5 frontend redesign are complete.

Milestone 6 is complete and merged into `main`. `M6 PR1 — Dashboards/Cards Backend Foundation`, `M6 PR2 — Dashboard/Card UI`, `M6 PR3 — CSV Export Backend`, `M6 PR4 — Card Refresh & CSV Export UI`, and `M6 PR5 — Card Reordering & Layout Persistence` plus the final Admin restricted-export policy are complete. PR #24 merged PR5. Milestone 7 — Product UX & Dashboard Redesign is active. M7 PR1 is complete and merged through PR #25. M7 PR2 is complete and merged through PR #26. M7 PR3 — Dashboard Editor, Grid & Visualizations is complete and merged through PR #27. M7 PR4 — Ask Data Redesign & Final UX Hardening is active on `feature/m7-ask-data-responsive-polish`. Milestone 8 has not started.

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

Milestone 6 PR2 added frontend dashboard/card API clients and types, read-only My Dashboard loading, personal dashboard creation UI, inline Ask Data Save as Card UI, and a safe read-only Dashboard Catalog UI. PR2 is complete and merged into `main`.

Milestone 6 PR3 — CSV Export Backend is complete and merged into `main`. It added controlled query-run and dashboard-card CSV export, export-time SQL validation, current-viewer PostgreSQL RLS, the dedicated read-only runtime role, CSV injection protection, safe filenames, successful export audit persistence, and PostgreSQL-backed export tests.

Milestone 6 PR4 — Card Refresh & CSV Export UI is complete and merged into `main`. It added frontend CSV downloads for successful Ask Data results and dashboard cards, secure dashboard-card refresh under the current viewer's `UserAccessContext`, automatic/manual refresh UI, safe table previews, and viewer-owned refresh `QueryRun` persistence without raw row snapshots.

Milestone 6 PR5 — Card Reordering & Layout Persistence persists card order through `DashboardCard.position` for owned personal dashboards only. It requires strict full-card-set validation, atomic updates, stale-layout conflict handling, dnd-kit pointer/keyboard ordering, explicit Move Up / Move Down controls, optimistic rollback, and refresh/export regression coverage. It must not expand `DashboardCard.layout` into a grid or resizing system.

The final Milestone 6 export policy adds `can_export_restricted_results` only to Admin through the deterministic permission catalog. Analyst still requires every referenced resource to be queryable and exportable. Admin restricted export requires both export permissions and may override only `is_exportable=false`; missing resources and `is_queryable=false` remain hard denials. Never hardcode the Admin role in export logic or bypass SQL validation, `queryops_query_runtime`, read-only execution, current-viewer RLS, row limits, CSV sanitization, ownership/visibility, or successful audit persistence. Restricted override usage must be audited without SQL or raw rows.

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

M7 PR1 and M7 PR2 are complete and merged. M7 PR2's backend/frontend Home aggregate and dashboard-browser boundaries must be preserved. PR2 introduced no Alembic migration, database table, or schema change.

M7 PR1 implemented only:

* real URL routing for `/login`, `/`, `/ask`, `/profile`, and permission-gated `/admin/role-requests`
* My Dashboard as authenticated home
* a dark-first responsive shell with persistent light mode
* navigation containing only active capabilities
* Profile with the existing Role Upgrade flow for eligible non-Admin users
* transitional My Dashboard cleanup using existing dashboard APIs

M7 PR2 implemented only:

* `GET /api/v1/home/overview` with personal product metrics for every authenticated user
* scoped operational aggregates for effective scoped-data permissions and global aggregates for effective global-data permissions
* independent permission gating for `can_manage_users`, `can_approve_role_requests`, and `can_view_global_audit` Admin metrics
* `GET /api/v1/dashboards/library` with Owned/Shared classification and safe preview-card metadata
* `GET /api/v1/dashboards/{dashboard_id}` with safe ordered card metadata and safe not-found behavior
* role-aware Home, library search/filter/sort, accessible preview dialog, real `/dashboards/:dashboardId`, compact personal creation, and preserved M6 refresh/export/reorder compatibility

M7 PR2 security rules:

* Operational aggregates must use `UserAccessContext`, existing `DataResource` records, `evaluate_access(...)`/`authorize_resource_access(...)`, the non-owner read-only runtime role, `build_rls_context(...)`, `set_rls_context(...)`, and PostgreSQL RLS.
* Resource authorization is independent. Return null for a forbidden metric without revealing table or policy internals.
* Never join or associate `app_users` to `directory_users` by email, name, provider id, or inferred identity.
* User receives no operational domain metrics and no Admin metrics.
* Home, library, preview, and detail must not expose SQL, raw operational rows, raw card config, raw card layout, permission internals, owner email, or sensitive event detail.
* Preserve the existing `dashboard_is_visible` policy across catalog, library, detail, refresh, and export. Foreign personal and archived dashboards remain unavailable.
* Preserve existing current-viewer RLS refresh, controlled CSV export, and owned-personal full-card-set reorder behavior wherever those capabilities remain reachable.

Out of scope for M7 PR2 unless explicitly requested:

* card resizing
* x/y grid coordinates
* width or height persistence
* advanced `DashboardCard.layout` behavior
* database migrations, schema changes, new tables, or seed-policy expansion
* Recharts or any additional charting/component library
* charts, visualization rendering, card resizing, grid coordinates, or advanced layout behavior
* View/Edit editor, Add Card, card context menus, rename, duplicate, remove, or dashboard cloning
* department/global dashboard creation UI
* Ask Data redesign, templates consolidation, or five-query history drawer
* actions
* approvals
* notifications
* Users UI
* Audit UI
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

Do not show future or placeholder destinations in navigation. Templates, Role Upgrade as a standalone destination, Query History, SQL / Technical, Department Dashboards, Admin Console, Users, and Audit must remain absent from navigation in PR2. Frontend permission visibility is UX only; backend authorization remains the source of truth.

Use the term Scope in general product UI. Department remains valid in the IT Operations domain model, internal permission names, and V1 compatibility API names, but must not be presented as the product's universal governance concept.

Local `docs/planning/` documents may be updated for M7 PR3 because the user explicitly authorized it. They remain ignored and must never be staged or committed.

M7 PR3 is implementation-complete and owns only the full-dashboard editor, responsive versioned grid, visualization recommendation/rendering, safe dashboard/card actions, and Add Card flows described in `PROJECT_PLAN.md`. Retain the following rules through review and merge.

M7 PR3 guardrails:

* Every dashboard or card mutation must independently enforce backend dashboard manageability and effective permissions; frontend capability checks are UX only.
* Layout updates require dashboard/card row locks, a complete current card set, strict 12/6/1 breakpoint validation, no overlaps, approved size presets, optimistic `layout_version` concurrency, atomic commit, and safe conflict responses.
* `DashboardCard.layout` and `DashboardCard.config` may contain only the approved versioned layout and sanitized visualization shapes. Never accept or expose arbitrary config JSON.
* Never persist query-result rows in card config/layout, local storage, URL state, SavedQuery metadata, or another new snapshot store.
* SQL source requires effective `can_view_sql`, dashboard visibility, and a deterministic latest-successful linked QueryRun. Return only original question and stored sanitized/executed SQL.
* Refresh/export continue through the existing secure endpoints and must retain current-viewer `UserAccessContext`, SQL validation, validator-sanitized SQL, `queryops_query_runtime`, read-only execution, PostgreSQL RLS, row limits, CSV sanitization, and successful export audit persistence.
* Card removal deletes only the `DashboardCard`. Preserve `SavedQuery` and every `QueryRun`.
* Dashboard archive is soft deletion. Duplicates are new personal dashboards/cards that reuse SavedQuery references and never duplicate QueryRuns or raw rows.
* Keep the legacy order-only `PATCH /api/v1/dashboards/my/layout` contract compatible while the new versioned full-layout endpoint is added.
* Do not implement cross-dashboard card movement, shared-dashboard layout personalization, arbitrary freeform resize, custom chart colors/formulas, dashboard restore/sharing mutation, or department/global dashboard creation UI.
* Do not redesign Ask Data or add the PR4 history drawer.
* Do not add Actions, Approvals, Audit UI, Users UI, notifications, real LLM providers, Supabase Auth, Redis/background jobs, or Milestone 8 behavior.

M7 PR4 is active and owns only the command-first Ask Data redesign, final responsive/accessibility hardening, focused Playwright E2E/CI coverage, and the dashboard drag-handle regression described in `PROJECT_PLAN.md`.

M7 PR4 guardrails:

* Ask Data remains at `/ask` with composer → current result → progressive details as its primary hierarchy. Templates and the five most recent own query runs live in accessible drawers/full-screen mobile sheets, not permanent columns or standalone routes.
* Quick history must call the own-history endpoint with `limit=5`, `offset=0`, and `include_sql=false`. Never use scope/department history for the drawer, expose another user's run, or render an `Open result` action.
* Historic QueryRun result rows are intentionally not persisted. Never restore, fabricate, or persist them in card config/layout, local storage, URL state, SavedQuery metadata, or another snapshot store.
* Templated reruns must resolve the saved `metadata.template_id` against the currently allowed template catalog and use that template's current approved question. Free reruns require effective `can_run_free_query`. Modified approved questions must clear template association.
* Reuse the PR3 visualization engine, compatibility logic, recommended configuration helpers, and renderer. Do not introduce duplicate inference rules. Ask Data Visual/Table choice is in-memory only, and Table is the safe fallback.
* Save and Export share a compact result toolbar. CSV continues through the secure backend endpoint. Save targets personal dashboards only and persists a safe recommended visualization through the existing card update endpoint without storing rows.
* SQL and Diagnostics require effective `can_view_sql`; User and Manager technical content must be absent from the DOM. Frontend permission checks improve UX only and never replace backend authorization.
* Scope display uses serialized scopes, default/global scope metadata, and effective permissions. Do not use `user.role === "admin"` to infer scope.
* Preserve backend auth, CSRF, dashboard manageability, SQL validation, validator-sanitized SQL, `queryops_query_runtime`, read-only execution, current-viewer RLS, row limits, CSV sanitization, export auditing, and restricted-export policy.
* Do not change backend endpoints, database schema/migrations, seed behavior, permissions, RLS, or API response shapes. If an existing contract is insufficient, stop and report the exact gap before implementation.
* Final M7 gates include the role matrix, stale-response protections, unit/integration tests, responsive desktop/tablet/mobile checks, keyboard/focus/accessibility checks, dark/light and reduced-motion checks, focused Playwright E2E, deterministic E2E CI, frontend build, full PostgreSQL backend suite, Alembic check, diff review, and CodeRabbit/manual review.
* Do not add Actions, Approvals, Audit UI, Users UI, notifications, real LLM providers, Supabase Auth, Redis/background jobs, or any Milestone 8 behavior.

M7 PR4 is expected to complete Milestone 7 only after every completion gate passes. Milestone 8 remains next and not started.

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
