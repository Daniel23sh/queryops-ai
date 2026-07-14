# QueryOps AI — Project Plan

## 1. Current Development Status

The current milestone status is:

`Milestone 6 — Dashboards, Cards & CSV Export` is complete and merged into `main` through PR #24.

Current PR scope:

`M7 PR1 — Product Shell, Routing & Navigation` is complete and merged into `main` through PR #25.

`M7 PR2 — Role-Aware Home & Dashboard Browser` is complete and merged into `main` through PR #26.

`M7 PR3 — Dashboard Editor, Grid & Visualizations` is active on branch `feature/m7-dashboard-editor-visualizations`.

M7 PR4 has not started. Milestone 8 has not started.

Milestone 0 foundation work, Milestone 1 database and IT Operations seed work, Milestone 2 auth/users/roles/permissions work, Milestone 2.5 Access Context Foundation, Post-Milestone 2.5 hardening, Milestone 3 RLS & Security Foundation, Milestone 4 Query Engine Backend, and Milestone 5 Ask Data UI/frontend redesign are complete.

Milestone 5 PR6 has been merged into `main`. M5 Ask Data and the M5 frontend redesign are complete. Milestone 6 is complete: M6 PR1 through PR5, including the final Admin restricted-export policy, are merged into `main`; PR #24 merged PR5. Milestone 7 — Product UX & Dashboard Redesign is active.

Milestone 2.5 delivered:

- `access_scopes`
- `user_access_scopes`
- `data_resources`
- `UserAccessContext`
- `AccessDecision`
- `evaluate_access(subject, action, resource, context)`
- scope-friendly permission aliases while retaining existing department permission keys
- `/auth/me` and demo login scope serialization
- role upgrade request compatibility with optional requested scope metadata

Milestone 3 delivered:

- scope-aware PostgreSQL RLS for IT Operations domain tables
- `SET LOCAL` RLS context helper
- DB session/helper integration for future Query Engine use
- initial security and RLS tests
- policy helper refinements where needed

Milestone 4 delivered:

- Domain Pack Loader
- Query Templates API
- `LLMProvider` interface
- `MockLLMProvider`
- SQL generator wrapper
- Schema Context Builder
- SQL validator
- runtime RLS role hardening with `queryops_query_runtime`
- scoped read-only Query Executor
- internal Query Engine orchestration service
- Query Run API
- `QueryRun` persistence
- PostgreSQL/RLS query tests
- security regression and deterministic MockLLM evaluation tests

Milestone 4 preserved the existing Access Context Foundation and PostgreSQL RLS behavior while adding only backend query-engine capabilities.

Milestone 5 PR1 was completed on branch `feature/m5-fix-m4-query-backend-compliance`. That branch closed the remaining Milestone 4 backend compliance gaps before any frontend Ask Data UI work began.

Milestone 5 PR1 completed:

- `POST /api/v1/queries/{query_run_id}/clarify`
- `GET /api/v1/queries/scope-history`
- `GET /api/v1/queries/department-history` as a V1 compatibility alias
- deterministic self-correction in the backend query engine
- hardened safe query metadata needed by the future Ask Data UI

Milestone 5 PR1 did not add frontend Ask Data UI, a real LLM provider, dashboards, CSV export, actions, approvals, or notifications.

Milestone 5 PR2 is complete on branch `feature/m5-ask-data-api-clients`. This branch adds frontend-safe Ask Data types and API clients for query templates, query runs, clarification, own history, scope history, and the department-history compatibility alias. It does not add Ask Data UI or backend behavior.

Milestone 5 PR3 is complete on branch `feature/m5-ask-data-shell`. This branch adds the static Ask Data page shell, split workspace layout, role-aware composer states, and disabled future operational placeholders. It does not call Query API clients, run browser queries, change backend behavior, or add Tailwind.

Milestone 5 PR4 is complete on branch `feature/m5-ask-data-query-integration`. This branch adds browser query execution through Ask Data: real template loading, selected-template runs, free-query runs for Manager/Analyst/Admin, User template-only behavior, result tables, loading/error/no-row/truncated/warning states, clarification flow, and a safe visualization suggestion placeholder. PR4 does not change backend behavior, add SQL/technical tabs, add Tailwind, or implement dashboards/cards, CSV export, actions, approvals, notifications, real LLM providers, Supabase Auth, or domain pack expansion.

Milestone 5 PR5 is complete on branch `feature/m5-ask-data-role-tabs-tests`. This branch adds Ask Data role-gated SQL and Diagnostics tabs. Analyst/Admin can view generated/executed SQL in the SQL tab and safe technical diagnostics in the Diagnostics tab. User/Manager cannot view SQL tabs, Diagnostics tabs, generated SQL, executed SQL, or technical diagnostics. PR5 also adds final Ask Data role matrix tests for User, Manager, Analyst, and Admin. PR5 does not add Tailwind, dashboard card persistence behavior, CSV export behavior, action preview behavior, approvals, notifications, real LLM providers, API keys, Supabase Auth, Redis/background jobs, or domain pack expansion.

Milestone 5 PR6 is merged into `main`. This branch added the Tailwind UI foundation, class-based light/dark mode, redesigned app shell/sidebar, redesigned Dashboard, focused Ask Data command workspace, lightly polished remaining frontend pages, and final CSS/docs cleanup. PR6 did not change backend behavior, auth/roles/RLS, query execution, dashboard card persistence behavior, CSV export behavior, action preview behavior, approvals, notifications, real LLM providers, API keys, Supabase Auth, Redis/background jobs, domain pack expansion, UI component libraries, or charting libraries.

Milestone 6 PR1 includes the dashboard catalog backend endpoint, my dashboard backend endpoint, dashboard creation backend endpoint, saving successful owned query runs as dashboard cards, safe metadata-only serializers, auth, CSRF, strict payload validation, dashboard visibility/manageability checks, and backend tests. Responses remain metadata-only and do not execute cards or expose SQL beyond the existing role-based SQL visibility rules.

Milestone 6 PR2 is complete and merged into `main`. It added frontend dashboard/card API clients and types, read-only My Dashboard loading, personal dashboard creation UI, inline Ask Data Save as Card UI, and a safe read-only Dashboard Catalog UI.

Milestone 6 PR3 — CSV Export Backend is complete and merged into `main`. It added controlled query-run and dashboard-card CSV export, export-time SQL validation, current-viewer PostgreSQL RLS, the dedicated read-only runtime role, CSV injection protection, safe filenames, successful export audit persistence, and PostgreSQL-backed export tests.

Milestone 6 PR4 — Card Refresh & CSV Export UI is complete and merged into `main` as `5b4d04c`. PR4 added frontend CSV downloads for successful Ask Data query runs and dashboard cards, a secure dashboard-card refresh endpoint that revalidates and executes stored SQL under the current viewer's `UserAccessContext`, automatic and manual card refresh UI, and safe table previews. Successful refreshes create viewer-owned linked `QueryRun` records without persisting raw result rows.

Milestone 6 PR5 — Card Reordering & Layout Persistence is complete. It adds ordered personal-dashboard cards through `DashboardCard.position`, secure full-card-set persistence with `PATCH /api/v1/dashboards/my/layout`, optimistic frontend reordering, dnd-kit pointer and keyboard support, explicit Move Up / Move Down controls, and refresh/export regressions. It does not turn `DashboardCard.layout` into a grid or resizing system.

Final Milestone 6 export policy: Analyst retains `can_export_results` and may export only reports whose referenced resources are all queryable and exportable. Admin additionally receives `can_export_restricted_results`, allowing audited export of reports that reference normally non-exportable resources only when every referenced resource remains queryable. The base export permission, SQL validation, runtime role, read-only execution, current-viewer RLS, row limits, CSV sanitization, ownership/visibility checks, and successful audit persistence remain mandatory. Missing resources and `is_queryable=false` are hard denials for every role.

Explicitly out of scope for M6 PR5:

- card resizing
- x/y grid coordinates
- width or height persistence
- advanced `DashboardCard.layout` behavior
- scheduled refresh
- department/global dashboard creation UI
- catalog starring
- dashboard cloning
- Save as Card modal
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion
- Full ABAC
- ReBAC
- policy builder UI
- dynamic policy engine
- masking
- tenant/project/region governance

Actions, approvals, audit UI, notifications, real LLM/API-key support, and Supabase Auth remain deferred unless explicitly requested. The former Actions, Approvals & Audit Milestone 7 is now Milestone 8. Milestone 7 is the active Product UX & Dashboard Redesign milestone.

## 2. Product Summary

QueryOps AI is a governed conversational data workspace. It will let users ask natural-language questions over structured data, receive safe SQL-backed results, save useful results as cards and dashboards, and eventually trigger controlled operational actions.

The product direction includes:

- Natural-language queries over structured business data.
- Safe, validated, read-only SQL execution.
- Result tables, charts, saved cards, and dashboards.
- Controlled operational actions.
- Approval workflows.
- Audit logs.
- Role-aware access to data and technical details.

The first domain is IT Operations, with data such as users, departments, licenses, devices, support tickets, groups, security events, and audit events. IT Operations is the first domain pack, not the whole product. The core system should remain generic so future domain packs can be added without rewriting the engine.

## 3. Source Documents

The full planning documents are local-only under `docs/planning/`. They are intentionally ignored by Git and should be used by local agents when available.

Do not commit the planning documents. Do not modify them unless explicitly asked.

Expected local planning documents:

- `01-product-brief.md`
- `02-mvp-prd.md`
- `03-technical-architecture.md`
- `04-it-operations-domain-pack.md`
- `05-security-permissions-matrix.md`
- `06-actions-approvals-audit.md`
- `07-api-contract.md`
- `08-ui-flows-wireframes.md`
- `09-evaluation-testing-plan.md`
- `10-development-milestones.md`

If filenames differ slightly, infer by number and title.

## 4. Non-Negotiable Product Decisions

Locked decisions from the planning documents:

- Use a monorepo.
- Frontend stack: React, TypeScript, and Vite.
- Backend stack: FastAPI and Python.
- Primary database: PostgreSQL.
- Use Docker Compose for local development.
- Database stack: SQLAlchemy 2 and Alembic.
- Seed data must be deterministic and Faker-based.
- Supabase Auth with Google OAuth is planned later.
- Use demo auth first for local development and early milestones.
- Store internal QueryOps roles, departments, and permissions in local PostgreSQL.
- PostgreSQL Row-Level Security is required in a later milestone, not Milestone 1.
- Use an LLM provider abstraction in later milestones.
- Do not call an LLM directly from business logic.
- Do not allow direct LLM database mutations.
- Natural-language SQL must be read-only and validated before execution.
- Actions must use deterministic backend logic in later milestones.
- Actions require preview, policy check, approval, execution, and audit in later milestones.
- IT Operations is the first domain pack, not a product hard-coding target.
- The frontend never talks directly to PostgreSQL or an LLM.
- The backend is the source of truth for permissions and policy enforcement.
- My Dashboard is the authenticated home route.
- Frontend navigation uses real URL routes and never advertises placeholder destinations.
- Product UI uses the term Scope; Department remains an implementation/domain concept rather than the general product label.
- The product shell is dark-first with a persistent light option.
- Profile contains Role Upgrade for eligible non-Admin users; Admin does not see Role Upgrade.
- Admin navigation exposes only implemented capabilities. Users and Audit remain hidden until real screens are implemented.
- M7 PR1 was frontend-only and is complete and merged.
- M7 PR2 added safe Home aggregates and dashboard library/detail contracts without schema changes and is complete through PR #26.
- M7 PR3 adds the explicit View/Edit dashboard editor, versioned responsive layouts, approved visualizations, safe dashboard/card mutations, and Add Card flows.
- M7 PR3 mutations must use effective permissions and dashboard manageability checks; frontend capability checks remain UX only.
- Card refresh/export must continue to use current-viewer `UserAccessContext`, validator-sanitized SQL, `queryops_query_runtime`, read-only execution, transaction-local PostgreSQL RLS, row limits, CSV sanitization, and existing audit behavior.
- SQL source is returned only with effective `can_view_sql`, and no raw result rows may be persisted in `DashboardCard.layout`, `DashboardCard.config`, local storage, or URL state.
- An `app_user` must never be associated with a `directory_user` by email, name, provider id, or any inferred identity for Home metrics.
- Home, dashboard library, preview, and detail responses must not expose SQL, raw operational rows, raw card config, or raw card layout.

## 5. Milestone 1 Scope

Milestone 1 includes database foundation work only:

- Database configuration.
- SQLAlchemy setup.
- Alembic setup.
- Database engine and session helper.
- Product schema.
- IT Operations domain schema.
- Alembic migrations.
- Deterministic seed script.
- Small seed profile for CI and fast local tests.
- Medium seed profile for local development and demo-scale data.
- Faker-based synthetic data generation.
- Deterministic seed behavior using a fixed random seed.
- Migration tests.
- Seed tests.
- Basic relationship tests.
- README updates only after real commands exist.

Expected product schema areas:

- Application users.
- Roles and permissions.
- Role upgrades.
- Saved queries and query runs.
- Dashboards and dashboard cards.
- Approval request records.
- Notification records.
- Evaluation run/result records.
- Application audit log records.

Expected IT Operations domain schema areas:

- Departments.
- Directory users.
- Login events.
- Licenses and license assignments.
- Devices and software installs.
- Support tickets.
- Groups and user group memberships.
- Security events.
- IT audit events.

Milestone 1 may define tables for later product capabilities, but it must not implement their runtime behavior yet.

## 6. Explicitly Out of Scope for Milestone 1

Do not implement the following in Milestone 1:

- Supabase Auth.
- Google OAuth.
- Real login or session flow.
- Runtime role or permission enforcement.
- PostgreSQL RLS policies.
- Natural-language-to-SQL pipeline.
- Real LLM calls.
- Query templates API.
- Dashboards UI.
- Cards UI.
- CSV export behavior.
- Actions.
- Approvals.
- Notifications behavior.
- Audit behavior beyond table definitions if audit tables are part of the schema.
- Evaluation engine behavior.
- Production deployment.

If a future feature needs a placeholder, keep it inert and clearly non-functional.

## 7. Target Repository Structure

Expected structure after Milestone 1:

```text
queryops-ai/
  backend/
    app/
      api/
      core/
      db/
      models/
    alembic/
      versions/
    scripts/
      seed_it_operations.py
    tests/
      test_health.py
      test_migrations.py
      test_seed.py
    alembic.ini
    pyproject.toml

  frontend/
    src/
    package.json

  docs/
    planning/        # local/private, ignored by Git

  README.md
  PROJECT_PLAN.md
  AGENTS.md
  docker-compose.yml
  .env.example
  .gitignore
```

Adjust exact file placement only when the repository has already established a reasonable convention. Keep the database foundation simple and avoid broad abstractions before they are needed.

## 8. Database Foundation Requirements

Milestone 1 should establish:

- SQLAlchemy 2 metadata/model conventions.
- A database engine/session helper for backend code and tests.
- Alembic configured to use the project metadata.
- Database configuration sourced from safe environment variables.
- PostgreSQL-compatible migrations.
- Tests that can create the schema from scratch.

Do not add request-time authorization, RLS context helpers, policy engines, or query engine logic in this milestone.

## 9. Schema Requirements

Product tables should support planned QueryOps platform concepts without implementing their behavior yet.

Domain tables should model the IT Operations pack and keep domain-specific concepts separate from generic product tables.

Relationships should be explicit enough to support later query, permission, dashboard, action, and evaluation milestones. Basic relationship tests should verify important foreign keys and seed consistency.

Audit-related tables may be defined as schema, but audit-writing behavior is not part of Milestone 1.

## 10. Seed and Testing Requirements

Seed data must be deterministic.

Milestone 1 seed requirements:

- Use Faker for realistic synthetic values.
- Use a fixed seed value so repeated runs produce stable output.
- Provide a small profile suitable for CI.
- Provide a medium profile suitable for local development and demos.
- Include realistic IT Operations relationships.
- Include deterministic domain anomalies needed by later evaluation questions.
- Document or test stable row counts.

Milestone 1 tests should cover:

- Migrations run from scratch.
- Small seed loads successfully.
- Medium seed loads successfully.
- Seed output is deterministic.
- Core relationships are valid.
- CI remains green.

## 11. Development Rules for Agents

Agents working in this repository must:

- Read this file before coding.
- Use local `docs/planning/` when available.
- Implement only the requested milestone or task.
- Follow the active milestone in this file.
- Stop and report any task that is outside the active milestone instead of implementing it.
- Do not add unplanned scope.
- Keep changes small and reviewable.
- Update README only when real commands or behavior change.
- Do not commit ignored planning docs.
- Do not modify `docs/planning/` unless explicitly asked.
- Do not commit secrets.
- Do not introduce real LLM calls before requested.
- Do not implement future milestones early.
- Prefer boring, maintainable structure over clever abstractions.

If a task request conflicts with this file, clarify the intended milestone before implementing broad product behavior.

## 12. Planned Branch and PR Breakdown for Milestone 1

Planned Milestone 1 branches:

1. `feature/m1-db-foundation`
   - Update project plan and agent docs.
   - Add DB foundation and Alembic setup.

2. `feature/m1-product-schema`
   - Product SQLAlchemy models.
   - Product migrations.
   - Basic product schema tests.

3. `feature/m1-domain-schema`
   - IT Operations domain models.
   - Domain migrations.
   - Relationship tests.

4. `feature/m1-seed-data`
   - Deterministic seed script.
   - Small seed profile.
   - Medium seed profile.
   - Seed verification tests.

5. `feature/m1-db-tests-docs`
   - Final migration, seed, and relationship checks.
   - README updates.
   - Milestone 1 compliance review.

Current task: first documentation-only commit on `feature/m1-db-foundation`, `Update plan for Milestone 1`.

## 13. Milestone 1 Acceptance Criteria

Milestone 1 is complete when:

- Database can be created from scratch.
- Alembic migrations run successfully.
- Product tables exist.
- IT Operations domain tables exist.
- Small seed profile loads successfully.
- Medium seed profile loads successfully.
- Seed output is deterministic.
- Stable row counts are documented or tested.
- Basic relationships are valid.
- CI remains green.
- No private planning docs are committed.
- `git status` is clean after commit.

Milestone 1 should leave the repository ready for auth, permission, and RLS work without implementing those later milestones early.

## 14. Milestone Status

The latest completed product milestone is:

`Milestone 6 — Dashboards, Cards & CSV Export`, merged into `main` through PR #24.

The active milestone and latest PR status are:

`Milestone 7 — Product UX & Dashboard Redesign`

`M7 PR1 — Product Shell, Routing & Navigation` is complete and merged into `main` through PR #25.

`M7 PR2 — Role-Aware Home & Dashboard Browser` is complete and merged through PR #26. `M7 PR3 — Dashboard Editor, Grid & Visualizations` is active on `feature/m7-dashboard-editor-visualizations`. M7 PR4 has not started. Milestone 8 has not started.

## 15. Milestone 6 Implementation Plan

Use one branch per PR, do not include PR numbers in branch names, split every PR into checkpoints, and end each checkpoint with its own commit. Do not create one large commit for an entire PR.

### PR1: Dashboards/Cards Backend Foundation

Branch:

```text
feature/m6-dashboards-cards-backend
```

Goal:

Add the first small backend foundation for dashboards and cards using the existing `dashboards`, `saved_queries`, `dashboard_cards`, and `query_runs` schema.

Status:

Complete and merged into `main`.

In scope for PR1:

- `GET /api/v1/dashboards/catalog`
- `GET /api/v1/dashboards/my`
- `POST /api/v1/dashboards`
- `POST /api/v1/query-runs/{query_run_id}/save-card`
- metadata-only dashboard/card serialization
- backend permission, ownership, visibility, CSRF, and SQL-leakage tests

Out of scope for PR1:

- CSV export
- card refresh execution
- dashboard/card frontend UI
- drag-and-drop UI
- action previews
- action requests
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

Checkpoints:

1. Checkpoint 1 — Verify updated `main`, create branch, and update `PROJECT_PLAN.md` / `AGENTS.md` status only.
2. Checkpoint 2 — Add dashboards route skeleton, serializers/helpers, route registration, and basic auth/CSRF tests.
3. Checkpoint 3 — Add catalog, my dashboard, create dashboard behavior, and permission/visibility tests.
4. Checkpoint 4 — Add save-card endpoint, persistence tests, and SQL leakage regression tests.
5. Checkpoint 5 — Final cleanup, full backend test run, `git diff --check`, and final status report.

### PR2: Dashboard/Card UI

Branch:

```text
feature/m6-dashboard-ui
```

Goal:

Prepare and implement the frontend dashboard/card experience in small checkpoints on top of the M6 PR1 backend foundation.

Status:

Complete and merged into `main`. Checkpoint 1 frontend dashboard/card API clients and types is complete. Checkpoint 2 read-only My Dashboard loading is complete. Checkpoint 3 personal dashboard creation is complete. Checkpoint 4 Ask Data Save as Card UI is complete. Checkpoint 5 added a safe, read-only Dashboard Catalog UI using the existing Department Dashboards navigation slot.

Checkpoint 1 in scope:

- frontend dashboard/card API response and request types
- `GET /api/v1/dashboards/catalog` client
- `GET /api/v1/dashboards/my` client
- `POST /api/v1/dashboards` client
- `POST /api/v1/query-runs/{query_run_id}/save-card` client
- focused frontend API client tests

Out of scope for Checkpoint 1:

- dashboard UI implementation
- Save as Card modal
- card grid UI
- drag-and-drop UI
- CSV export
- card refresh execution
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

Checkpoint 2 in scope:

- load `GET /api/v1/dashboards/my` from the existing Dashboard page
- render owned personal dashboards and cards as safe read-only metadata
- loading, empty, and error states
- frontend tests for loading, empty, rendering, error, role coverage, and SQL non-exposure

Out of scope for Checkpoint 2:

- Dashboard Catalog UI
- Create Dashboard UI
- Save as Card modal
- Ask Data save-card integration
- drag-and-drop UI
- CSV export
- card refresh execution
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

Checkpoint 3 in scope:

- inline Dashboard page UI for creating personal dashboards
- `POST /api/v1/dashboards` with `visibility_scope: "personal"`
- permission guardrail for users without `can_create_personal_dashboard`
- CSRF-backed submit, client-side empty-title validation, safe success/error states
- refresh `GET /api/v1/dashboards/my` after successful creation
- frontend tests for permission behavior, request body/header, refetch, rendering, and SQL non-exposure

Out of scope for Checkpoint 3:

- Dashboard Catalog UI
- department/global dashboard creation UI
- Save as Card modal
- Ask Data save-card integration
- drag-and-drop UI
- CSV export
- card refresh execution
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

Checkpoint 4 in scope:

- render inline Save as Card UI in Ask Data after a successful query result
- require `can_create_card` before showing the active save UI
- load existing personal dashboards from `GET /api/v1/dashboards/my`
- submit `POST /api/v1/query-runs/{query_run_id}/save-card` with `card_type: "table"`
- safe loading, empty, success, and generic error states
- frontend tests for role gating, saveability gating, request body/header behavior, URL encoding, and SQL non-exposure

Out of scope for Checkpoint 4:

- Dashboard Catalog UI
- department/global dashboard selection UI
- Save as Card modal
- drag-and-drop UI
- CSV export
- card refresh execution
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

Checkpoint 5 in scope:

- load `GET /api/v1/dashboards/catalog` from the existing Department Dashboards navigation item
- render dashboards visible to the current user according to backend catalog results
- safe metadata-only dashboard and card previews
- loading, empty, and generic error states
- frontend tests for endpoint loading, empty/rendered/error states, and SQL/result-row non-exposure

Out of scope for Checkpoint 5:

- department/global dashboard creation UI
- catalog starring
- dashboard cloning
- drag-and-drop UI
- CSV export
- card refresh execution
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

### PR3: CSV Export Backend

Branch:

```text
feature/m6-csv-export-backend
```

Goal:

Build the backend CSV export surface in small checkpoints, starting with safe API foundation, then query-run CSV execution, dashboard card CSV execution, and successful export audit persistence while deferring frontend UI.

Status:

Complete and merged into `main`.

Current checkpoint in scope:

- real CSV response for `POST /api/v1/query-runs/{query_run_id}/export-csv`
- real CSV response for `POST /api/v1/cards/{card_id}/export-csv`
- authentication, CSRF, strict payload validation, export permission, dashboard visibility checks, export-time SQL validation, `DataResource.is_exportable` policy checks, existing validated SQL executor boundary, CSV serialization, and CSV injection sanitization
- successful export audit persistence for query-run and dashboard-card CSV exports using safe metadata-only `AppAuditLog` rows
- hardened string/header CSV injection protection, trusted numeric preservation, printable-ASCII filenames capped at 255 characters, and response construction before audit persistence
- focused and PostgreSQL-backed tests for auth, CSRF, payload validation, permission overrides, visibility, linked query-run eligibility, export policy, CSV response behavior, SQL non-exposure, runtime role, read-only execution, current-viewer RLS, CSV injection protection, and successful audit persistence

Out of scope for the current checkpoint:

- frontend export UI
- card refresh execution
- drag-and-drop
- M6 PR4 work
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

### PR4: Card Refresh & CSV Export UI

Branch:

```text
feature/m6-card-refresh-export-ui
```

Goal:

Add secure current-viewer dashboard-card refresh and the frontend CSV export experience while keeping dashboard results session-scoped and deferring layout changes.

Status:

Complete and merged into `main` as `5b4d04c`.

Completed checkpoints:

1. PR4 status and download API foundation
2. Ask Data query-run export UI
3. Card refresh backend
4. PostgreSQL/RLS refresh hardening
5. Dashboard card refresh/export UI
6. Full verification, documentation, and cleanup

In scope for PR4:

- raw/download frontend API support and safe Blob downloads
- Ask Data CSV export for successful authorized query runs
- dashboard-card CSV export through the existing backend export endpoint
- `POST /api/v1/cards/{card_id}/refresh`
- stored SQL revalidation and execution under the current viewer's `UserAccessContext`
- PostgreSQL runtime-role, read-only, and RLS refresh tests
- successful viewer-owned refresh `QueryRun` persistence without raw rows
- automatic one-time card refresh on personal dashboard load
- manual card refresh with previous in-memory result retention on failure
- safe table previews, empty/loading/success/error states, and accessibility tests

Out of scope for PR4:

- drag-and-drop or card reordering
- `PATCH /api/v1/dashboards/my/layout`
- layout persistence or card resizing
- persistent raw result snapshots or new snapshot tables
- scheduled refresh, background jobs, or Redis
- dashboard/card starring or cloning
- department/global dashboard creation UI
- actions, approvals, notifications, M7 work, or real LLM/Auth expansion

### PR5: Card Reordering & Layout Persistence

Branch:

```text
feature/m6-card-reorder-layout
```

Goal:

Persist the order of cards in each owned personal dashboard while retaining PR4 refresh and CSV export behavior.

Status:

Complete and merged into `main` through PR #24. Milestone 6 is complete.

In scope for PR5:

- `PATCH /api/v1/dashboards/my/layout`
- strict full-card-set request validation with contiguous zero-based positions
- current-user ownership checks for one non-archived personal dashboard per request
- atomic `DashboardCard.position` updates and stale-layout conflict handling
- dnd-kit pointer and keyboard reordering inside one dashboard only
- explicit accessible Move Up / Move Down controls
- optimistic update, rollback, reload-on-conflict, and refresh/export regressions
- explicit Admin-only `can_export_restricted_results` for audited exports of queryable but normally non-exportable reports
- unchanged Analyst exportability policy and hard denial of missing or non-queryable resources

Out of scope for PR5:

- cross-dashboard movement
- department/global dashboard reordering
- card resizing, x/y coordinates, width/height persistence, or advanced `layout` use
- starring, cloning, scheduled refresh, Redis/background jobs
- actions, approvals, notifications, real LLM/API-key support, Supabase Auth, domain expansion, or M7 work

PR5 passed backend, frontend, PostgreSQL/Alembic, medium-seed API QA, production build, diff, and CodeRabbit review gates. Milestone 6 is complete.

## 16. Milestone 7 Implementation Plan

Milestone 7 — Product UX & Dashboard Redesign is active. It modernizes the frontend experience on top of the completed Milestone 6 backend without starting Actions, Approvals & Audit, which are deferred to Milestone 8.

Milestone 7 is split into four PRs:

1. `M7 PR1 — Product Shell, Routing & Navigation`
   - Complete and merged into `main` through PR #25.
   - Frontend-only routed shell, dark-first responsive navigation, Profile and Role Upgrade consolidation, and transitional My Dashboard cleanup.
2. `M7 PR2 — Role-Aware Home & Dashboard Browser`
   - Complete and merged into `main` through PR #26.
   - Adds real role-aware Home overview data and the dashboard browser/detail experience, including `/dashboards/:dashboardId` with a real detail screen.
3. `M7 PR3 — Dashboard Editor, Grid & Visualizations`
   - Active on `feature/m7-dashboard-editor-visualizations`.
   - Adds explicit View/Edit modes, responsive versioned grid layouts, constrained drag/resize behavior, visualization recommendation/rendering, safe dashboard/card actions, and Add Card sources.
4. `M7 PR4 — Ask Data Redesign & Final UX Hardening`
   - Not started.
   - Delivers the command-first Ask Data redesign, templates/history consolidation, and final UX hardening.

### M7 PR1 Locked Scope

- `/` is My Dashboard and the authenticated home.
- Implement real routes for `/login`, `/`, `/ask`, `/profile`, and `/admin/role-requests`.
- Do not add `/dashboards/:dashboardId` until PR2 provides a real dashboard detail page.
- Navigation shows only implemented destinations: My Dashboard, Ask Data when `can_use_query_templates`, Profile, and permission-gated Admin → Role Requests when `can_approve_role_requests`.
- No future or placeholder navigation items are rendered, including Templates, Query History, SQL / Technical, Department Dashboards, Admin Console, Users, or Audit.
- Use Scope terminology in product UI. Department-specific names may remain in domain and compatibility APIs.
- Use a dark-first responsive shell with a persistent light option, accessible mobile drawer behavior, 44×44 minimum touch targets, and reduced-motion handling.
- Profile contains the existing Role Upgrade workflow for User, Manager, and Analyst. Admin sees no Role Upgrade heading, message, form, or own-request API load.
- Frontend permission checks improve UX only; backend authorization remains authoritative.
- PR1 may reuse only existing frontend API contracts. If required Profile or route data is missing from `/auth/me`, stop and request approval before any backend change.
- PR1 must not implement Home Overview metrics, dashboard library filters/previews/details, visualizations, resizing/grid coordinates, Ask Data redesign, Actions, Approvals, notifications, Users UI, Audit UI, or any Milestone 8 work.

### M7 PR2 Locked Scope

Goal: Role-Aware Home & Dashboard Browser.

Implementation status: complete and merged into `main` through PR #26. PR2 added the three read-only APIs below, scoped/global Home aggregates through the existing read-only runtime/RLS boundary, the Owned/Shared browser and accessible metadata preview, the direct dashboard detail route, compact personal creation, and explicit owned-personal reorder compatibility. No schema change, charting library, editor, resize behavior, Ask Data redesign, or Milestone 8 work was added.

In scope:

- `GET /api/v1/home/overview` with a personal product summary for every authenticated user.
- Manager/Analyst operational aggregates across every department scope authorized by their effective permissions and `UserAccessContext`.
- Admin global operational aggregates plus independently permission-gated active app-user, pending role-request, and recent application-audit counts.
- Resource-by-resource authorization, transaction-local PostgreSQL RLS, the non-owner read-only runtime role, read-only transactions, and null metrics when a resource is unavailable.
- `GET /api/v1/dashboards/library` with non-archived visible dashboards classified as `owned` or `shared`.
- Dashboard title/description client-side search, All/Owned/Shared filters, and Recently updated/Name/Created sorting.
- A metadata-only dashboard preview dialog that never refreshes cards, executes queries, exports data, or exposes SQL/config/layout/raw rows.
- `GET /api/v1/dashboards/{dashboard_id}` and authenticated `/dashboards/:dashboardId` with safe ordered card metadata.
- Full dashboard presentation with existing current-viewer card refresh and permission-gated CSV export behavior.
- Explicit owner-only reorder compatibility for owned personal dashboards using the existing M6 layout endpoint and conflict handling.
- Compact personal dashboard creation with existing permission and CSRF behavior.
- Responsive desktop/tablet/mobile behavior, including an accessible full-screen mobile preview dialog.

Security and data semantics:

- `app_users` and `directory_users` remain separate identities. Do not match them by email, full name, provider id, or another inferred attribute.
- User receives the personal product summary and scope display metadata only; operational and admin metrics are null.
- Home never returns employee, device, license, ticket, security-event, SQL, or raw-row detail.
- Active human users are human, active-employment, active-account directory users.
- Device compliance uses `devices.compliance_status`; no devices produces a null rate.
- Monthly license cost includes active assignments and `licenses.monthly_cost_usd` under viewer RLS.
- Unused licenses reuse the approved 60-day active, non-mandatory template semantics.
- Open support tickets are `open` or `in_progress`.
- Recent security events use `security_events.occurred_at` for the last 30 days.
- Dashboard visibility continues to use the existing `dashboard_is_visible` policy; foreign personal and archived dashboards never appear.
- Static `/dashboards/my`, `/dashboards/catalog`, and `/dashboards/library` routes must precede the UUID detail route.

Out of scope:

- database migrations, new tables, or schema changes; stop and report if one becomes necessary
- charts, Recharts, visualization rendering, grid coordinates, resizing, or advanced layout behavior
- the PR3 View/Edit editor, Add Card, card context menus, rename, duplicate, remove, dashboard cloning, or scoped/global dashboard creation UI
- Ask Data redesign, query history drawer, or PR4 work
- Actions, Approvals, Audit UI, Users UI, notifications, real LLM providers, Supabase Auth, Redis/background jobs, or Milestone 8 work

### M7 PR3 Locked Scope

Goal: Dashboard Editor, Grid & Visualizations.

Implementation status: active on `feature/m7-dashboard-editor-visualizations`.

In scope:

- Explicit View mode by default and capability-gated Edit mode on `/dashboards/:dashboardId`.
- A `dashboards.layout_version` migration for optimistic concurrency; no new layout table.
- Strict versioned `DashboardCard.layout` with desktop 12-column, tablet 6-column, and mobile 1-column coordinates.
- Complete-card-set, non-overlapping, breakpoint-safe layout validation with atomic row locks, a single version increment, and deterministic `position` derivation.
- Responsive drag/reorder and constrained resize on desktop/tablet; mobile uses Move Up/Move Down and approved size presets without free drag-resize.
- Safe visualization configuration for KPI, Table, Bar, Line, Area, Donut, Semicircle gauge, Stacked bar, and Status list.
- Deterministic recommendation from in-memory refreshed result data, compatible manual overrides, reset-to-recommended, and safe Table fallback without deleting a saved preference.
- Effective-permission/dashboard-manageability capabilities and independent backend authorization for every mutation.
- Dashboard rename, personal duplicate, and soft archive; card rename, visualization update, duplicate, remove, source, refresh, and CSV export.
- Source responses limited to original question and stored sanitized/executed SQL, gated by effective `can_view_sql` and dashboard visibility.
- Accessible card context menus on the full route only, with right-click, menu button, Shift+F10, keyboard navigation, Escape, outside click, and focus restoration.
- Add Card from authorized query templates and bounded eligible own successful query history through the existing query, save-card, refresh, and RLS boundaries.
- Existing `PATCH /api/v1/dashboards/my/layout` order-only compatibility, existing PR2 Home/library/metadata preview, and existing secure refresh/export behavior.

Security and persistence rules:

- Backend authorization, dashboard manageability, `UserAccessContext`, application policy, and PostgreSQL RLS remain authoritative.
- Do not hardcode role names where effective permissions/capabilities apply.
- Never accept or expose arbitrary config JSON, user SQL, raw result rows, diagnostics, runtime details, or policy internals.
- Never persist refreshed result rows in card config/layout, local storage, or URL state.
- Layout saves require `expected_layout_version`, lock the dashboard and current cards, validate the complete set, and fail with `DASHBOARD_LAYOUT_CONFLICT` on stale state.
- Card removal deletes only `DashboardCard`; SavedQuery and QueryRun history remain intact.
- Dashboard archive is soft deletion; dashboard/card duplication reuses SavedQuery references and does not duplicate QueryRuns.
- Refresh/export retain validator revalidation, the non-owner read-only runtime role, current-viewer RLS, row caps, CSV sanitization, and export audit semantics.

Out of scope:

- cross-dashboard card movement or duplication
- per-user/shared-dashboard layout personalization
- arbitrary freeform sizes, chart formulas, or custom color editors
- persisted query-result rows or snapshot storage
- dashboard restore, sharing mutation, or department/global dashboard creation UI
- Ask Data redesign or the five-item query history drawer (M7 PR4)
- Actions, Approvals, Audit UI, Users UI, notifications, real LLM providers, Supabase Auth, Redis/background jobs, or Milestone 8

M7 PR4 remains not started. Milestone 8 remains not started. Do not begin either from PR3 scope.
