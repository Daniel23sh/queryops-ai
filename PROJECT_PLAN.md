# QueryOps AI — Project Plan

## 1. Current Development Status

The current milestone status is:

`Milestone 6 — Dashboards, Cards & CSV Export` is complete and merged into `main` through PR #24.

Current PR scope:

`M7 PR1 — Product Shell, Routing & Navigation` is complete and merged into `main` through PR #25.

`M7 PR2 — Role-Aware Home & Dashboard Browser` is complete and merged into `main` through PR #26.

`M7 PR3 — Dashboard Editor, Grid & Visualizations` is complete and merged into `main` through PR #27.

`M7 PR4 — Ask Data Redesign & Final UX Hardening` is complete and merged into `main` through PR #28. Milestone 7 is complete.

`Milestone 8 — Actions, Approvals & Audit` is complete. M8 PR1 through PR5 are complete and merged through PR #33. `M8 PR6 — Approvals, Audit & Notifications UX` is complete and merged through PR #34; `main` reached `73531f25f4d234cabc1f509931492ea62b78d8df`. `M8 PR7 — E2E, Security Hardening & Completion` is implementation- and verification-complete on `feature/m8-e2e-security-completion` but is not merged. The next milestone has not started.

Milestone 0 foundation work, Milestone 1 database and IT Operations seed work, Milestone 2 auth/users/roles/permissions work, Milestone 2.5 Access Context Foundation, Post-Milestone 2.5 hardening, Milestone 3 RLS & Security Foundation, Milestone 4 Query Engine Backend, and Milestone 5 Ask Data UI/frontend redesign are complete.

Milestone 5 PR6 has been merged into `main`. M5 Ask Data and the M5 frontend redesign are complete. Milestone 6 is complete: M6 PR1 through PR5, including the final Admin restricted-export policy, are merged into `main`; PR #24 merged PR5. Milestone 7 — Product UX & Dashboard Redesign is complete.

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

Actions, approvals, audit UI, notifications, real LLM/API-key support, and Supabase Auth remained deferred through Milestone 7. The former Actions, Approvals & Audit Milestone 7 is now Milestone 8 because Product UX & Dashboard Redesign became Milestone 7. Milestone 8 completed the approved seven-PR sequence in Section 17; PR1 through PR6 are merged and PR7 is implementation- and verification-complete but not merged.

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

`Milestone 7 — Product UX & Dashboard Redesign`, complete and merged through PR #28.

The latest PR status is:

`Milestone 7 — Product UX & Dashboard Redesign`

`M7 PR1 — Product Shell, Routing & Navigation` is complete and merged into `main` through PR #25.

`M7 PR2 — Role-Aware Home & Dashboard Browser` is complete and merged through PR #26. `M7 PR3 — Dashboard Editor, Grid & Visualizations` is complete and merged through PR #27. `M7 PR4 — Ask Data Redesign & Final UX Hardening` is complete and merged through PR #28.

`Milestone 8 — Actions, Approvals & Audit` is complete. M8 PR1 through PR5 are complete and merged through PR #33. M8 PR6 is complete and merged through PR #34. M8 PR7 is implementation- and verification-complete on `feature/m8-e2e-security-completion` but is not merged. The next milestone has not started.

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

Milestone 7 — Product UX & Dashboard Redesign is complete. It modernizes the frontend experience on top of the completed Milestone 6 backend without starting Actions, Approvals & Audit, which remain deferred to Milestone 8.

Milestone 7 is split into four PRs:

1. `M7 PR1 — Product Shell, Routing & Navigation`
   - Complete and merged into `main` through PR #25.
   - Frontend-only routed shell, dark-first responsive navigation, Profile and Role Upgrade consolidation, and transitional My Dashboard cleanup.
2. `M7 PR2 — Role-Aware Home & Dashboard Browser`
   - Complete and merged into `main` through PR #26.
   - Adds real role-aware Home overview data and the dashboard browser/detail experience, including `/dashboards/:dashboardId` with a real detail screen.
3. `M7 PR3 — Dashboard Editor, Grid & Visualizations`
   - Complete and merged into `main` through PR #27.
   - Adds explicit View/Edit modes, responsive versioned grid layouts, constrained drag/resize behavior, visualization recommendation/rendering, safe dashboard/card actions, and Add Card sources.
4. `M7 PR4 — Ask Data Redesign & Final UX Hardening`
   - Implementation-complete on `feature/m7-ask-data-responsive-polish`.
   - Delivers the command-first Ask Data redesign, templates/history consolidation, PR3 visualization reuse, final responsive/accessibility hardening, and focused Playwright E2E/CI coverage.
   - Expected to complete Milestone 7 after every unit, integration, E2E, build, PostgreSQL, Alembic, accessibility, responsive, documentation, and review gate passes.

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

Implementation status: complete and merged into `main` through PR #27.

Delivered implementation:

- Alembic migration `0007_dashboard_layout_version.py` adds non-null `dashboards.layout_version` with default `1` while retaining per-card `position`, safe `layout`, and sanitized `config` storage.
- Detail capabilities and independently authorized dashboard/card mutation endpoints implement rename, personal duplicate, soft archive, visualization changes, duplicate/remove, source view, and expected-version full-layout persistence.
- The responsive editor uses Recharts and React Grid Layout for the approved nine visualization types and 12/6/1 layouts, with mobile movement/size controls and accessible dashboard/card menus and dialogs.
- Add Card supports approved templates and eligible recent successful own query results through the existing Query Engine, Save as Card, refresh, permission, RLS, and audit boundaries.
- Verification completed with 639 PostgreSQL-backed backend tests, 192 frontend tests, a production build, Alembic upgrade/check, deterministic medium-seed role/viewpoint QA, diff checks, and a zero-finding manual full-diff review after CodeRabbit timed out.

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

### M7 PR4 Locked Scope

Goal: Ask Data Redesign & Final UX Hardening.

Implementation status: complete on `feature/m7-ask-data-responsive-polish`.

Delivered implementation:

- Replace the permanent split layout with a command-first `/ask` hierarchy: compact page header, dominant composer, current result, then progressive details.
- Move approved templates into an accessible desktop drawer/full-screen mobile sheet with client-side search and category filters.
- Add a lazy own-history drawer that requests exactly five items through `GET /api/v1/queries/history?limit=5&offset=0&include_sql=false`.
- Allow history to rerun only currently allowed templates or permitted free questions; never claim to restore historic result rows.
- Reuse PR3 `inferVisualization`, compatibility helpers, and renderer for in-memory Visual/Table switching. Do not duplicate inference rules or persist the temporary view choice, recommendation, mapping, or rows.
- Consolidate Save to Dashboard and backend CSV export into one compact result toolbar.
- Replace the inline Save as Card panel with an accessible personal-dashboard dialog and persist the safe recommended visualization through the existing card update endpoint after save.
- Preserve the latest stable successful result across export, save, and clarification action failures, with generation guards against stale query/action/drawer responses.
- Replace permanent result tabs with progressive Summary and permission-gated SQL/Diagnostics content. User and Manager technical content must be absent from the DOM.
- Harden clarification context, the dashboard drag-handle regression, responsive behavior, keyboard/focus behavior, dark/light themes, reduced motion, and cross-product accessibility.
- Add focused Chromium Playwright coverage and a deterministic E2E CI job while keeping existing backend/frontend jobs.
- Update README and milestone documentation only after the implemented behavior and all completion gates pass.

Security and persistence rules:

- Backend authorization, dashboard manageability, `UserAccessContext`, SQL validation, `queryops_query_runtime`, read-only execution, transaction-local PostgreSQL RLS, row limits, CSV sanitization, and export audit remain authoritative and unchanged.
- Quick history uses the current user's own-history endpoint only and always sets `include_sql=false`; no scope/department history endpoint is used.
- Historic QueryRun rows do not exist and must not be restored, fabricated, or persisted in card config/layout, local storage, URL state, or another snapshot store.
- Template-only users cannot submit free questions, stale template IDs, or modified approved questions as template runs.
- SQL and Diagnostics remain gated by effective `can_view_sql`; frontend permission checks are UX only.
- Scope labels come from serialized scopes/default scope/effective permissions, never from `role === "admin"`.
- Save targets personal dashboards only, reuses existing APIs, and treats visualization configuration failure as a safe partial success.

Out of scope:

- backend endpoints, response-shape changes, database migrations, seed changes, permission changes, or RLS changes; stop and report before any such change
- chat-style conversation, persisted historic result snapshots, query cancellation, a new visualization engine, or full dashboard visualization editing in Ask Data
- department/global dashboard save targets, cross-dashboard movement, dashboard editor expansion, custom chart formulas/colors, or scheduled refresh
- Actions, Approvals, Audit UI, Users UI, notifications, real LLM providers, Supabase Auth, Redis/background jobs, or any Milestone 8 behavior

Completion evidence: 184 frontend tests, the production frontend build, four deterministic Chromium Playwright flows, 639 PostgreSQL-backed backend tests, Alembic no-diff verification, responsive/focus/theme checks, and manual full-diff review all pass. The final CodeRabbit rerun was unavailable because the free CLI rate limit was reached after valid findings from earlier passes were fixed and retested. No backend, migration, seed, permission, RLS, or API-contract changes were made. The local medium seed was restored after QA.

Milestone 7 is complete and merged through PR #28.

## 17. Milestone 8 Implementation Plan

The original private planning document numbered Actions, Approvals & Audit as Milestone 7. It is Milestone 8 in this authoritative plan because Product UX & Dashboard Redesign became Milestone 7.

Milestone 8 is split into seven approved PRs:

1. `M8 PR1 — Action Persistence & Engine Contracts`
2. `M8 PR2 — Reclaim License Preview & Request Flow`
3. `M8 PR3 — Approval Execution, Audit & Notifications`
4. `M8 PR4 — Disable Inactive User & Backend Security Completion`
5. `M8 PR5 — Requester Actions UX`
6. `M8 PR6 — Approvals, Audit & Notifications UX`
7. `M8 PR7 — M8 E2E, Security Hardening & Completion`

M8 PR1 is complete and merged through PR #29. M8 PR2 is complete and merged through PR #30. M8 PR3 is complete and merged through PR #31. M8 PR4 is complete and merged through PR #32. M8 PR5 is complete and merged through PR #33. M8 PR6 is complete and merged through PR #34. M8 PR7 is implementation- and verification-complete on `feature/m8-e2e-security-completion` but is not merged. Milestone 8 is complete; the next milestone has not started.

### M8 PR1 — Action Persistence & Engine Contracts

Branch:

```text
feature/m8-action-engine-foundation
```

Status: complete and merged into `main` through PR #29.

Goal: establish the non-destructive database foundation and typed deterministic backend contracts required by later Milestone 8 work without exposing or executing an action workflow.

In scope:

- Alembic revision `0008_action_engine_foundation` based on `0007_dashboard_layout_version`
- `action_requests` lifecycle persistence with generic scope snapshots, preview/policy snapshots, guarded statuses, priority, counts, failure details, idempotency, and timestamps
- non-destructive action-workflow extensions to `approval_requests` while retaining QueryRun compatibility
- explicit action audit fields on `app_audit_logs` while preserving existing audit writers and generic `audit_metadata`
- nullable `it_audit_events.actor_app_user_id` alongside the existing directory actor identity
- verification that the existing notifications schema can represent the locked M8 notification contract
- SQLAlchemy models, enums, foreign keys, indexes, constraints, and explicit relationships matching the migration
- typed action handler contracts, a fail-closed explicit registry, and pure permission/scope-based action policy decisions
- the minimum stable access-action vocabulary for action request/approval and scope/global audit decisions
- focused SQLite migration/model, registry, policy, permission, seed, and access-policy tests, plus full PostgreSQL regression verification

Guardrails:

- Backend authorization and effective permission keys are authoritative; policy must not rely only on role-name comparisons.
- Scoped decisions require the exact assigned scope key. A reference resource without a scope key is never sufficient for scoped action authorization.
- `app_users` and `directory_users` remain separate identity systems. Never infer a mapping using email, name, provider ID, or another heuristic, and never place an app-user ID in `it_audit_events.actor_user_id`.
- The action registry is an explicit allowlist. It cannot dynamically import user-controlled modules or accept arbitrary mutation SQL or callables from an LLM.
- No operational rows are mutated, no QueryRun result rows are persisted, and PR1 does not write future preview snapshots.
- Existing query, dashboard, export, PostgreSQL RLS, role-request audit, CSV export audit, and seed reset behavior must remain compatible.
- The migration must preserve existing approval, notification, and audit rows, upgrade from 0007, downgrade to 0007, and make no RLS-policy or seed-reset changes.
- Keep changes backend-only except for committed milestone-control documentation.

Acceptance criteria:

- `action_requests` and all required constraints, indexes, foreign keys, lifecycle fields, scope snapshots, and relationships are present.
- One approval request per action request is enforced while existing QueryRun approval compatibility remains intact and approval status supports `expired`.
- Action audit fields and the distinct nullable operational `actor_app_user_id` foreign key are present without breaking existing audit writers.
- Existing notifications are proven usable for recipient, type, title/body, related action or approval, unread/read state, and created/read timestamps without unnecessary schema replacement.
- Supported action types, statuses, priorities, and approval statuses have dedicated stable constants/enums.
- Typed handler registration succeeds; unknown and duplicate registration fail closed; lookup performs no domain work.
- Request, scoped approval, global/cross-scope approval, override, self-approval, threshold, and exact-scope decisions return stable structured results based on effective permissions.
- Focused foundation tests and the full backend, PostgreSQL/Alembic, frontend unit, and frontend build regressions pass.
- Documentation records exact delivered scope and verification before the PR is marked implementation-complete.

Explicit exclusions:

- action API endpoints or response schemas
- real reclaim or disable previews, eligibility queries, revalidation implementations, or domain handlers
- approval execution, domain mutations, audit writing, or notification delivery
- frontend code, action suggestions, navigation, Actions/Approvals/Audit screens, or notification UI
- execution-log tables, queues, Redis, schedulers, background jobs, or automatic rollback actions
- RLS-policy changes, Supabase Auth, real LLM providers, full ABAC, ReBAC, policy languages, or policy-builder UI
- the complete release-blocking 20-action workflow suite, which is completed across M8 PR3, PR4, and PR7
- any M8 PR2 or later implementation

Delivered implementation:

- Migration `0008_action_engine_foundation` adds the `action_requests` lifecycle table with the two supported action types, eight locked statuses, three priorities, generic scope plus Department compatibility, access/decision/preview/policy/skipped snapshots, guarded non-negative counts, unique idempotency, failure details, timestamps, foreign keys, and targeted indexes.
- `approval_requests` retains every legacy column and QueryRun relationship while adding nullable `action_request_id`, `required_approver_role`, `expires_at`, one-approval-per-action uniqueness, and the `expired` status.
- `app_audit_logs` retains generic `audit_metadata` and existing writers while adding nullable action/approval, Department/scope, severity, changed-field before/after, and self-approval fields with useful lookup indexes.
- `it_audit_events.actor_user_id` remains a nullable `directory_users` foreign key; the separate nullable `actor_app_user_id` points to `app_users` for future QueryOps actors.
- The existing notifications schema was retained unchanged and is tested for recipient, notification type, title/body, generic related action/approval, unread/read status, and created/read timestamps.
- SQLAlchemy adds dedicated action type, action request status, priority, and approval status enums plus explicit requester, source QueryRun, scope, Department, approval, audit, and reverse relationships. Seed reset includes action requests in dependency-safe deletion order.
- `app/action_engine` adds immutable typed preview/revalidation/execution descriptors, a three-stage `ActionHandler` protocol, an explicit empty fail-closed allowlist registry, and pure structured request/approval policy decisions.
- The access policy vocabulary now covers action request, scoped/global/override approval, and scoped/global audit. Scoped action and audit decisions require an exact scope key and cannot use a scope-less reference resource as authorization.

Completion evidence:

- Focused action persistence, registry, policy, access, and product-schema suite: 71 passed.
- Default backend suite: 606 passed, 77 PostgreSQL-only tests skipped.
- PostgreSQL-backed full backend suite: 683 passed with no skips or failures.
- Alembic upgraded `0007_dashboard_layout_version` to `0008_action_engine_foundation`; `alembic check` reported no new upgrade operations.
- The dedicated SQLite preservation test upgrades 0007 to head and downgrades head to 0007 while preserving pre-existing approval, notification, and application-audit rows and enforcing one approval per action request.
- A fresh temporary PostgreSQL database passed base-to-head upgrade, head-to-0007 downgrade, re-upgrade to head, and a no-diff Alembic check. The temporary database was removed; the existing user database was not downgraded, reset, or reseeded.
- Frontend regression suite: 188 passed across 28 files.
- Frontend TypeScript checks and production Vite build passed; only the existing large-chunk advisory was emitted.
- `git diff --check` and the full scope/security review passed.

No action endpoint, action suggestion, real preview, approval execution, notification delivery, audit writer, operational mutation, QueryRun result-row persistence, frontend behavior, or RLS-policy change exists in M8 PR1. The complete release-blocking 20-action workflow suite is not claimed complete. M8 PR2 — Reclaim License Preview & Request Flow was activated under the separate scope below and is now implementation-complete but not merged.

### M8 PR2 — Reclaim License Preview & Request Flow

Branch:

```text
feature/m8-reclaim-preview-request
```

Status: complete and merged into `main` through PR #30.

Goal: deliver the requester-side backend lifecycle for `reclaim_unused_license` through deterministic preview, persisted draft, submission, safe detail, pending-request cancellation, audit, approver notifications, and current-viewer PostgreSQL RLS without implementing approval decisions or operational execution.

In scope:

- `POST /api/v1/actions/preview` for `reclaim_unused_license` only
- `POST /api/v1/actions/request` to submit an owned unexpired draft
- `GET /api/v1/actions/{action_request_id}` with requester/eligible-approver safe visibility
- `POST /api/v1/actions/{action_request_id}/cancel` for an owned pending request
- deterministic current-row eligibility with explicit eligible, skipped, and Admin-override classifications
- 30-minute draft-preview expiration and 24-hour pending-approval expiration
- `action_preview_created`, `action_requested`, `action_cancelled`, and persisted-expiration audit events where applicable
- one pending `ApprovalRequest` per submitted action plus `action_pending_approval` notifications for effective eligible approvers
- exact assigned-scope authorization, independent authorization of `license_assignments`, `licenses`, and `directory_users`, and the existing non-owner read-only runtime/PostgreSQL RLS boundary
- optional owned succeeded QueryRun provenance that never selects targets, exposes SQL, or persists result rows
- strict payload validation with at most 100 unique explicit IDs across `target_user_ids` and `license_assignment_ids`

Locked reclaim behavior:

- Normal eligibility requires an active assignment, no recorded usage or usage older than 60 days, an authorized current scope, a human Directory User, and neither mandatory nor exception flags.
- `last_used_at IS NULL` means no recorded usage and is both eligible and high-confidence. Usage older than 90 days is also high-confidence.
- Reclaimed, suspended, missing, or structurally invalid records are skipped. Foreign-scope records are never disclosed to non-global requesters.
- Mandatory, exception, service-account, authorized cross-scope, and other explicitly locked override conditions are classified separately as Admin-override records.
- More than 20 eligible records remains a request-level `record_count_over_analyst_threshold` flag; it does not reclassify every record.
- Manager and Admin requests default to `high`; Analyst requests default to `normal`. Priority never bypasses approval policy.

Guardrails:

- The backend selects and revalidates current domain rows. LLM output, QueryRun rows, browser state, stored SQL, natural-language output, and client-supplied JSON never become an executable target set.
- State-changing endpoints require authentication, valid CSRF, effective `can_request_action`, current `UserAccessContext`, and exact scope authorization. Frontend visibility is not authorization.
- Every required domain resource is authorized independently. Domain reads use the established read-only `queryops_query_runtime` transaction, transaction-local RLS context, and PostgreSQL RLS; no owner-session shortcut is allowed.
- `app_users` and `directory_users` remain separate identities. No email, name, provider ID, or other heuristic may associate them.
- Persist only explicit minimum action-target and policy snapshots. Never persist QueryRun result rows, SQL, full Directory User rows, raw emails, permission catalogs, session data, or arbitrary request JSON.
- Preview/audit, submission/approval/notifications/audit, and cancellation/status/audit changes are atomic within their respective product transactions.
- PR2 adds no migration, frontend code, action suggestion, notification list/read API, approval decision, self-approval, execution path, domain mutation, domain audit event, queue, background job, or RLS-policy change.

Acceptance criteria:

- Unknown, misspelled, unsupported, or unregistered action types fail closed through a safe standardized error.
- Preview classification, Decimal savings, counts, exclusions, policy flags, snapshots, expiration, persistence, and safe serialization are deterministic and tested with a frozen clock.
- Explicit IDs are deduplicated, bounded, queried again from current state, and never trusted as rows. Scope-only selection deterministically evaluates current candidates in the authorized scope.
- Source QueryRun provenance must be owned, succeeded, and compatible with trusted reclaim metadata; foreign IDs receive safe not-found behavior and SQL is never returned.
- Submitting an owned unexpired draft produces exactly one pending approval, a 24-hour expiration, safe audit, and deduplicated eligible-approver notifications atomically. Repeated submit creates no duplicates.
- Safe detail is visible only to the requester or a currently eligible scoped/global approver. Other callers receive safe not-found behavior.
- Only the requester can cancel a pending request, and cancellation atomically cancels its pending approval and writes audit without changing any license assignment.
- Focused unit/API tests, real PostgreSQL/RLS tests, the full backend suite, Alembic upgrade/check, frontend tests/build, diff checks, and the CodeRabbit review gate pass.

Explicit exclusions:

- approval list, approve, reject, or execute endpoints
- `pending_approval -> approved_executing` or any completed/failed operational transition
- license assignment or other operational-domain mutation
- `it_audit_events` writes for domain changes
- notification delivery/list/read behavior or completion/decision notifications
- requester or approver frontend, navigation, suggested-action UI, or audit screens
- `disable_inactive_user`, M8 PR3 or later work, queues, schedulers, Redis, rollback actions, real LLM providers, or Supabase Auth

Completion evidence:

- The explicit registry now contains only the deterministic `ReclaimUnusedLicenseHandler`; `revalidate()` and `execute()` fail closed and no API can invoke them.
- The four requester-side endpoints deliver preview, submit, safe detail, and pending-request cancellation with strict schemas, standardized errors, authentication/CSRF, effective permission checks, exact scope authorization, safe ownership/not-found behavior, frozen 30-minute preview expiration, and 24-hour pending expiration.
- The handler re-queries current rows, classifies each examined record exactly once, treats null usage as eligible/high-confidence, uses strict older-than-60/90-day boundaries, separates Admin-override records, applies the over-20 rule at request level, and normalizes Decimal costs with half-up precision.
- Persisted snapshots are explicitly constructed and structurally validated before lifecycle writes. They contain no QueryRun rows, generated/executed SQL, raw email, complete Directory User row, session data, permission catalog, arbitrary request JSON, or internal database failure detail.
- Preview creation plus audit, submission plus one approval/eligible-approver notifications/audit, and cancellation plus approval cancellation/audit commit atomically. Duplicate submit produces no duplicate approval, notification, or audit side effect.
- Real PostgreSQL tests prove independent `directory_users`, `license_assignments`, and `licenses` authorization, Manager/Analyst scope isolation, foreign-selector nondisclosure, Admin global cross-scope classification, `queryops_query_runtime`, read-only transactions, transaction-local RLS without context leakage, product/domain RLS separation, and no `app_user`/`directory_user` identity inference.
- Focused reclaim handler suite: 19 passed. Focused actions API suite: 35 passed. Focused action PostgreSQL/RLS suite: 9 passed.
- Final default backend suite: 660 passed and 86 PostgreSQL-only tests skipped. Final disposable-PostgreSQL backend suite: 746 passed with no skips or failures.
- Alembic upgraded the disposable database to head and `alembic check` reported `No new upgrade operations detected`; PR2 adds no migration and the existing user database was not reset or reseeded.
- Frontend regression: 188 passed across 28 files. TypeScript checks and the production Vite build passed; only the existing large-chunk advisory was emitted.
- `git diff --check`, complete-diff inspection, and the required suspicious-pattern searches passed after fixes.
- Review method: **Manual CodeRabbit-style self-review — not a CodeRabbit result.** CodeRabbit CLI 0.6.5 was installed, but `coderabbit auth status --agent` reported unauthenticated; automatic login then timed out and the supported fallback remained blocked waiting for a manually copied browser token. Therefore no CodeRabbit issue count is claimed.
- The manual review found and fixed two Major issues: count-only persisted-snapshot validation that could permit a lifecycle write before serialization failed, and unexpected SQLAlchemy failures bypassing the standardized safe action error envelope. It also fixed one Minor issue: inconsistent per-record versus aggregate Decimal rounding. Regression tests cover all three. The repeated full review found no unresolved Critical, Major, or actionable in-scope Minor issue.

Known limitations remain intentional: there is no approval list/decision, revalidation, execution, license mutation, domain audit write, notification delivery/read API, action frontend, or background worker in PR2 itself. M8 PR3 — Approval Execution, Audit & Notifications is now implementation-complete under the separate scope below but is not merged.

### M8 PR3 — Approval Execution, Audit & Notifications

Branch:

```text
feature/m8-approval-execution-audit
```

Status: complete and merged into `main` through PR #31.

Goal: complete `reclaim_unused_license` end-to-end on the backend through permission-aware approval review, synchronous approve-and-execute, current-state revalidation, narrowly privileged PostgreSQL mutation, audit, notifications, and safe timeline/read APIs without starting the second action or frontend work.

In scope:

- `GET /api/v1/approvals/pending`, `GET /api/v1/approvals/{approval_id}`, `POST /api/v1/approvals/{approval_id}/approve`, and `POST /api/v1/approvals/{approval_id}/reject`
- dynamically authorized pending visibility, bounded pagination, priority/oldest sorting, safe approval detail, and lazy concurrency-safe expiration
- current-approver revalidation of every persisted reclaim target against current permissions, `UserAccessContext`, policy, RLS, and PostgreSQL rows
- a dedicated non-owner `queryops_action_runtime` role with `NOBYPASSRLS`, minimal read/column-update/domain-audit grants, and constant-controlled `SET LOCAL ROLE`
- scoped `license_assignments` UPDATE RLS using `USING` and `WITH CHECK`, plus scoped `it_audit_events` INSERT RLS using `WITH CHECK`
- optimistic pending-state claims, synchronous idempotent execution, a shared execution timestamp, and mutation of only assignment status/reclaimed fields
- atomic success persistence across approval, domain mutation, application/domain audit, notifications, skipped counts, and completion status
- rollback of every success-side effect on technical failure followed by a separate safe failed-status/audit/notification transaction
- `action_approved`, `action_rejected`, `action_executed`, `action_failed`, escalation, and domain `license_removed` audit behavior with changed fields only
- requester/approver/Admin-sensitive notification records plus current-recipient list, mark-read, and read-all APIs
- permission-aware `GET /api/v1/audit/logs` and safe persisted action timeline metadata
- deterministic PostgreSQL runtime-role, RLS, rollback, concurrency, idempotency, notification, audit, and the identifiable 20-case action-security suite

Database security decision:

- `queryops_query_runtime` remains strictly read-only and never executes an operational action.
- Deterministic domain mutation uses `queryops_action_runtime`, a non-owner, non-bypass role entered transaction-locally only after current approver authorization and revalidation.
- The action role receives only SELECT on `license_assignments`, `directory_users`, and `licenses`; column-level UPDATE of `license_assignments.status`, `reclaimed_at`, and `reclaimed_by_app_user_id`; and INSERT on `it_audit_events`.
- The application role returns from the action role before product-table approval, audit, notification, and lifecycle writes.

Guardrails:

- Effective permission keys and exact assigned scopes are authoritative. Manager approval is denied; scoped approval is limited to 20 records with no self/cross-scope/override approval; global, override, and Admin self-approval each require their dedicated permissions.
- Persisted preview data is review context, never current eligibility. Every target is re-queried and locked where needed; QueryRun SQL, generated/executed SQL, LLM metadata, and client-provided record state never select executable records.
- A newly discovered Admin condition escalates without claiming or mutating; zero currently executable records complete as a successful no-op with all records recorded as skipped.
- Approve and execute remain one success transaction. No commit occurs between decision, mutation, audit, notification, and completion; technical failures roll it all back before separate safe failure persistence.
- Only the three approved `LicenseAssignment` columns may change. No `app_user`/`directory_user` identity inference is permitted, and QueryOps approvers use `ItAuditEvent.actor_app_user_id` while `actor_user_id` stays null absent a genuine directory actor.
- Public responses and limited timelines never expose SQL, raw access snapshots, full permissions, raw rows, raw audit metadata, driver errors, credentials, stack traces, or internal failure detail.
- No frontend, `disable_inactive_user`, separate Execute endpoint, queue, scheduler, background worker, external notification delivery, rollback action, real LLM behavior, Supabase Auth, or M8 PR4+ implementation is allowed.

Acceptance criteria:

- Approval list/detail/reject/approve endpoints enforce auth, CSRF where state changes, strict schemas, current effective authorization, safe not-found, stable conflicts, and the locked sorting/visibility contract.
- Revalidation safely skips ordinary drift, escalates new override requirements without mutation, and executes only current authorized records through the action runtime and write-side RLS.
- Approve/approve, approve/reject, and approve/cancel races have one winner; completed, failed, rejected, cancelled, and expired requests cannot execute or create duplicate audit/notifications.
- Success, no-op, rejection, escalation, technical failure, and failure-persistence behavior are deterministic, safely serialized, and covered by unit/API and real PostgreSQL tests.
- Application audit, one domain audit per changed assignment, notification recipient/deduplication/read behavior, scoped/global audit visibility, and timeline metadata match the locked contracts.
- Migration previous-head/new-head round trips, Alembic no-diff check, full backend/PostgreSQL/frontend regressions, focused concurrency/runtime-role tests, diff checks, and the required review gate pass before PR3 is marked implementation-complete.

Explicit exclusions:

- `disable_inactive_user` or any directory-user mutation
- frontend Actions, Approvals, Audit, Notifications, navigation, badges, or timeline UI
- action suggestions, notification delivery outside database records, WebSockets, email, Slack, or push
- background jobs, scheduled execution, Redis, queues, automatic retries, automatic rollback actions, or an execution-log table
- real LLM behavior, LLM-selected executable records, arbitrary mutation SQL, Supabase Auth, or future M8 work

Implementation delivered:

- Migration `0009_action_runtime_role` creates the fixed `queryops_action_runtime` role as `NOLOGIN`, `NOINHERIT`, and `NOBYPASSRLS`; grants only schema usage, the three required domain-table SELECT grants, the three-column `license_assignments` UPDATE grant, and `it_audit_events` INSERT; grants the configured application login role explicit SET-only membership; installs role-scoped assignment UPDATE `USING`/`WITH CHECK` and domain-audit INSERT `WITH CHECK` policies; and reverses only those PR3 objects. A pre-existing action role fails closed instead of being altered or dropped.
- Pending approval list/detail, reject, and synchronous approve-and-execute routes use current effective permissions, exact scope matching, safe not-found behavior, bounded payloads/pagination, lazy expiration, priority sorting, and Manager/Analyst/global/override/self-approval rules from the action policy contracts.
- Revalidation re-queries and locks every deterministic assignment target plus related user/license policy dependencies under the current approver context. Persisted preview, QueryRun SQL, and LLM metadata never select execution rows. Ordinary eligibility drift is recorded as stable skips; a new override requirement escalates without claiming or mutation; an all-skipped set completes as a successful no-op.
- Approval claims retain conditional pending/expiration checks after row locks. Approve/approve, approve/reject, approve/cancel, expiration, and failure-persistence races preserve one terminal winner. Completed, failed, rejected, cancelled, and expired actions cannot execute again or duplicate audits/notifications.
- Reclaim execution runs synchronously through the action role, verifies current role/read-write/RLS state and row count, and changes only assignment `status`, `reclaimed_at`, and `reclaimed_by_app_user_id` with one shared timestamp. Success keeps approval, mutation, one `license_removed` domain audit per changed assignment, application audits, notifications, skipped counts, and completion in one transaction. Technical failure rolls that transaction back and persists safe failed status, audit, and notifications separately when the terminal claim is still available.
- `GET /api/v1/notifications`, current-recipient idempotent mark-read/read-all routes, permission-aware `GET /api/v1/audit/logs`, and persisted safe action timeline serialization are complete. Notification delivery remains database-only. App audit before/after data contains changed fields only; domain audit uses `actor_app_user_id` and never infers a directory actor.

Completion evidence:

- The exact release-blocking action-security matrix passed all 20 cases. The separately verbose runtime-role/concurrency selection passed 8 cases, including approve/approve, approve/reject, approve/cancel, expiration, and failure terminal-winner checks. Focused final PostgreSQL action preview/execution tests passed 44 cases, and disposable-database guard tests passed 9 cases.
- Default backend verification passed 686 tests with 132 expected PostgreSQL-only skips. The full disposable-PostgreSQL backend run passed all 818 tests. Frontend regression passed all 188 tests across 28 files, and TypeScript plus the production Vite build passed with only the pre-existing large-chunk advisory.
- On the disposable database, migration verification passed `0008_action_engine_foundation -> 0009_action_runtime_role -> 0008_action_engine_foundation -> 0009_action_runtime_role`; `alembic check` reported no pending operations. A separate pre-existing-role failure test confirmed the migration refuses to modify a pre-existing privileged role. No existing user database was reset or reseeded.
- Four CodeRabbit CLI reviews completed and reported 20 findings in total: 2 Critical, 16 Major, and 2 Minor. All valid findings were fixed in separate commits with regression coverage. Fixes included role/policy ownership and actor binding, explicit application-role membership, safe failure categorization, guarded expiration/failure claims, dependency locking and second revalidation, cumulative skips, cross-scope policy recomputation, exact grants/notification/concurrency assertions, migration-only schema setup, destructive-test opt-in/application-database protection, and canonical endpoint identity checks.
- A fifth CodeRabbit pass was rate-limited. After its stated cooldown, the final retry was rejected before launch, so the final post-fix gate used the authorized **Manual CodeRabbit-style self-review — not a CodeRabbit result**. The complete diff and required suspicious-pattern searches were reviewed across migration/grants/RLS, authorization, concurrency, revalidation, transactionality, mutation, audit, notifications, and failure handling; no remaining Critical, Major, or actionable in-scope Minor issue was found. No zero-finding CodeRabbit result is claimed.
- `git diff --check`, full diff/scope inspection, ignored-planning-file verification, and backend/frontend regression checks passed. No frontend source file or private planning document changed.

Known limitations at PR3 completion were intentional: PR3 supported only synchronous `reclaim_unused_license`; notifications were database records only; and it included no frontend action/approval/audit/notification UI. M8 PR4 later added `disable_inactive_user` and merged through PR #32. There is still no separate Execute endpoint, automatic retry, rollback action, worker, scheduler, queue, or Redis. If both execution and the separate safe failure-persistence transaction fail, the API returns a generic error and operational intervention is required.

### M8 PR4 — Disable Inactive User & Backend Security Completion

Branch:

```text
feature/m8-disable-inactive-user
```

Status: complete and merged into `main` through PR #32.

Goal: add the second and final V1 backend action, `disable_inactive_user`, by extending the deterministic PR1–PR3 action workflow without duplicating approval, execution, audit, notification, or concurrency orchestration.

In scope:

- deterministic preview, persisted snapshot validation, current-state revalidation, and synchronous execution for explicitly selected inactive human Directory Users
- a 90-day successful-login boundary; no successful-login history is inactive
- hard skips for service accounts, already disabled/non-active accounts, recent logins, missing or unsafe records
- Admin overrides for privileged humans, humans with open critical security events, and authorized cross-scope humans
- request-level Admin escalation above 20 actionable users without changing per-record classification
- a narrow action-runtime extension: SELECT only on required dependency tables, column UPDATE only for `directory_users.account_status` and `directory_users.updated_at`, and a role-scoped active-human-to-disabled RLS policy
- one `user_disabled` IT audit event per changed Directory User, existing application lifecycle audit, database notifications, safe timelines, optimistic claims, rollback, and separate safe failure persistence
- unit/API and real PostgreSQL coverage for eligibility, revalidation, exact scope, RLS/catalog grants, mutation limits, rollback, concurrency, audit, notifications, nondisclosure, and reclaim regression

Guardrails:

- Reuse the existing generic action endpoints and approve-and-execute workflow. Do not add a separate Execute endpoint or duplicate the reclaim lifecycle.
- Treat explicit UUIDs as selectors only. Current PostgreSQL rows, effective permissions, exact scope, transaction-local RLS, and the fixed action runtime remain authoritative.
- Service accounts are never executable through this action, including by Admin. A future service-account action requires a separate explicit action type.
- Never infer an AppUser/DirectoryUser identity, persist raw emails, login/security-event rows, SQL, QueryRun rows, arbitrary JSON, or raw database errors.
- Change only Directory User `account_status` and `updated_at`; retain atomic success, one-winner lifecycle, idempotency, audit, notification deduplication, and separate failure persistence.
- No frontend, navigation, additional action type, action suggestion, external delivery, queue, worker, scheduler, Redis, automatic retry/rollback, real LLM behavior, Supabase Auth, or M8 PR5+ work is allowed.

Delivered:

- Migration `0010_disable_inactive_user` extends the fixed non-owner action role with column-only dependency reads, Directory User `account_status`/`updated_at` UPDATE, and role/scope/state RLS while refusing unknown role attributes, memberships, ownership, or grants.
- The explicitly registered `disable_inactive_user` handler classifies active human users at a deterministic 90-day successful-login boundary. Service, disabled, recent, missing, and unsafe records are skipped; privileged, open-critical-event, and cross-scope humans require Admin override; over 20 is request-level only.
- Preview reads use `queryops_query_runtime`, a read-only transaction, transaction-local requester RLS, independently authorized resources, bounded explicit UUID selectors, and minimal structurally validated snapshots. QueryRun content never selects targets.
- Approval re-reads and locks current users and dependencies, performs a second action-role pass, forbids a newly executable set after dependency locking, recomputes scope/override policy, and reuses PR3's one-winner synchronous lifecycle.
- Execution changes only Directory User status/timestamp, writes one actor-separated `user_disabled` domain audit per mutation, and atomically persists lifecycle audit and database notifications. Technical failure rolls back success effects and uses PR3's separate safe failure transaction.
- Final verification passed 710 default backend tests with 150 expected PostgreSQL skips, all 860 disposable-PostgreSQL backend tests, the exact 20-case suite within 86 focused PostgreSQL action tests, fresh and round-trip migration/refusal/no-diff gates, 188 frontend regression tests, standalone TypeScript checks, and the production build. The final review was **Manual PR4 security and correctness review — not a CodeRabbit result**.

Intentional limitations remain: execution is synchronous; notifications are database-only; service accounts require a future separate action type; there is no action frontend, separate Execute endpoint, automatic retry/rollback, queue, worker, scheduler, Redis, or external delivery. If execution and separate failure persistence both fail, the API returns a generic error and operational intervention is required.

### M8 PR5 — Requester Actions UX

Branch:

```text
feature/m8-requester-actions-ux
```

Status: complete and merged into `main` through PR #33.

Goal: make the requester workflow usable from an approved Ask Data result through deterministic action recommendation, preview, submission, requester tracking, safe detail/timeline display, and pending-request cancellation.

In scope:

- explicit validated action-suggestion metadata on only the two approved action-aware query templates
- deterministic `suggested_actions` on current successful, non-truncated template results for users with effective `can_request_action`
- requester-owned metadata-only `GET /api/v1/actions` with bounded pagination, status grouping, safe counts, and SQL-level ownership isolation
- strict frontend action contracts and transient selector resolution from the current in-memory result only
- Suggested Action recommendation, accessible Preview Drawer, Submit for Approval, `/actions`, `/actions/:actionRequestId`, requester Home summary, persisted timeline, and pending cancellation
- Manager, Analyst, and Admin requester UX; User receives no action suggestion, CTA, navigation, or route access
- focused backend/frontend tests, full PostgreSQL and frontend regressions, Alembic no-diff verification, and manual responsive/accessibility QA

Guardrails:

- Backend permissions, scope authorization, RLS, action eligibility, approval policy, revalidation, execution, audit, notification, concurrency, and failure semantics remain authoritative and unchanged.
- Suggestions come only from explicit approved Domain Pack metadata. Free queries, historic rows, question text, column-name inference, LLM output, truncated/empty/failed results, and malformed selectors cannot create an action input.
- Result UUID selectors remain transient in memory and are never persisted in QueryRun metadata, local/session storage, URLs, dashboard config, or card layout.
- Reuse the existing preview/request/detail/cancel APIs and shared `AccessibleOverlay`; do not duplicate the action lifecycle, focus system, or add a separate Execute endpoint.
- PR5 has no schema, Alembic migration, seed, permission, or RLS changes.
- Do not add Approvals, Audit explorer, Notifications UI, approval decisions, external delivery, workers, queues, schedulers, Redis, retries, rollback actions, additional action types, or M8 PR6/PR7 work.

Delivered:

- Only `unused_licenses_by_department` and `inactive_users_by_department` carry validated, non-executable Domain Pack action metadata. Current successful non-truncated template responses expose safe deterministic `suggested_actions` only when the requester has effective `can_request_action`; no selector UUID is persisted in QueryRun metadata.
- `GET /api/v1/actions` enforces requester ownership in SQL, excludes unsubmitted drafts, validates bounded status/pagination filters, and returns safe metadata, counts, and next-step presentation only.
- The frontend resolves selectors only from the current in-memory visible result, deduplicates them in result order, fails closed on any malformed selector, and sends exactly one action-specific selector field to the existing preview endpoint.
- Ask Data now provides the Suggested Action card and accessible Preview Drawer; `/actions`, `/actions/:actionRequestId`, Home summary, safe timeline/detail, and pending cancellation reuse the existing generic lifecycle and shared overlay system. User remains excluded; Manager override records remain summary-only.
- Final verification passed 739 default backend tests with 150 expected PostgreSQL skips, all 889 disposable-PostgreSQL backend tests, the exact 20-case release-blocking suite, 222 frontend tests, standalone TypeScript checks, the production build, Alembic head/no-diff verification, and manual desktop/mobile browser QA across User, Manager, Analyst, and Admin. The final review was **Manual PR5 requester UX review — not a CodeRabbit result**.

Intentional limitations remain: approval decisions, Audit explorer, and Notifications UX are deferred to M8 PR6; cross-workflow E2E completion remains deferred to M8 PR7. Notifications stay database-only, execution stays synchronous, and there is no separate Execute endpoint, external delivery, retry/rollback action, queue, worker, scheduler, or Redis.

### M8 PR6 — Approvals, Audit & Notifications UX

Branch:

```text
feature/m8-approvals-audit-notifications-ux
```

Status: complete and merged into `main` through PR #34.

Goal: expose the existing permission-aware pending-approval, synchronous decision, scoped/global audit, and current-recipient database-notification capabilities through the website without changing backend authorization, action execution, persistence, or delivery semantics.

In scope:

- safe authorized totals for pending approvals, filtered notifications plus unread notifications, and audit results under the exact existing visibility and filter rules
- narrow typed frontend API clients for approvals, audit, and notifications with abort support and existing CSRF/error conventions
- permission-aware `/approvals`, `/approvals/:approvalId`, and `/audit` routes and navigation
- responsive pending approval review, safe approval detail, required-reason reject, and synchronous Approve and Execute UX
- role-aware audit list/filter/detail presentation using only fields explicitly returned by the backend
- an authenticated notification bell/drawer with unread count, current-recipient reads, safe related navigation, and mark-one/read-all behavior
- compact Analyst/Admin Home approval and Audit entry points plus shared non-persistent workflow activity counts
- focused/full frontend and backend regressions, disposable PostgreSQL/Alembic verification, manual browser QA, controlled cleanup, and a final manual PR6 review

Guardrails:

- Effective permission keys and backend responses remain authoritative. Frontend route/navigation checks are UX only, and approval counts must use the existing eligibility decision rather than a second policy implementation.
- Manager keeps requester Actions behavior but receives no Approvals controls or Audit access under the current backend permission contract, even though private documents 06–08 describe a future limited Manager audit view.
- Do not change action eligibility, current-state revalidation, dependency locking, execution transactions, runtime roles, RLS, lifecycle transitions, notification recipients, audit writing, snapshots, permissions, role mappings, migrations, or schema.
- Never render raw audit metadata, arbitrary notification payloads, SQL, QueryRun rows, access-context snapshots, permission catalogs, stack traces, driver errors, or internal failure details.
- Decision mutations require a current CSRF token, explicit bounded reason, duplicate-submit protection, authoritative response handling, and safe recovery for expiration, races, policy escalation, access loss, and execution failure.
- Shared activity state is in-memory, resets on authenticated-user changes, aborts stale reads, uses no polling, and cannot break page rendering when a badge request fails.
- No new frontend dependency, action type, separate Execute endpoint, retry/rollback action, external delivery, WebSocket, queue, worker, scheduler, Redis, real LLM behavior, Supabase Auth, Admin Users UI, Evaluation UI, or M8 PR7 work is allowed.

Delivered:

- exact authorization-aware approval, notification, unread, and filtered audit totals without changing lifecycle or access decisions
- typed abortable approval, audit, and notification clients plus in-memory user-resetting workflow activity state
- permission-aware Approvals and Audit routes/navigation, responsive pending review, safe approval detail, and CSRF-protected synchronous approve/reject dialogs
- scoped/global safe Audit browsing, an authenticated current-recipient notification drawer, deterministic related navigation, and idempotent mark-read controls
- Analyst/Admin Home workflow summaries and exact pending/unread badges, with Manager and User route/navigation exclusions preserved

Final verification passed 740 default backend tests with 150 expected PostgreSQL-only skips, all 890 disposable-PostgreSQL backend tests, the exact 20-case action-security suite within 86 focused PostgreSQL action tests, 23 focused approval API tests, 247 frontend tests, standalone TypeScript, the production build, fresh Alembic upgrade/head/no-diff verification, desktop role-matrix and 390px responsive browser QA, and live isolated Manager → Analyst/Admin decision workflows. The browser QA covered scoped rejection and execution, Admin override and self-approval, requester/approver notifications, exact mark-read counts, scoped/global Audit detail, a governed read confirming the domain change, protected routes, themes, focus restoration, overflow, and a clean browser console. The task-owned PostgreSQL container and browser/runtime processes were removed after verification.

The final **Manual PR6 correctness, scope, accessibility, and security-boundary review — not a CodeRabbit result** found 0 Critical, 0 Major, and 3 actionable Minor issues. All three were fixed: unknown future notification types now fail closed even with a valid action UUID, Audit renders both safe related targets when both are returned, and all current safe revalidation policy codes receive controlled copy. The controlled cleanup removed the unconsumed notification activity status state and its redundant updates; explicit route, permission, CSRF, overlay, abort, audit-field, and recipient boundaries were intentionally retained. No actionable finding remains.

The private planning documents describe a possible future limited Manager audit view, but the current backend grants Manager no audit permission. PR6 follows the authoritative effective-permission contract, so Manager has requester Actions and notifications but no Audit navigation or route.

Implementation checkpoints are `e3c31c5` (`docs: start m8 approvals audit notifications ux`), `b198b90` (`feat: add safe workflow activity metadata`), `91adede` (`feat: add approvals audit notification ux`), `ea9f999` (`fix: harden workflow ux boundaries`), `3a8aa77` (`docs: complete m8 approval activity ux`), and `e295861` (`test: strengthen workflow ux review coverage`).

No schema, migration, seed, permission, role mapping, RLS, runtime-role, action eligibility, revalidation, execution, lifecycle, audit-writing, notification-recipient, QueryRun, or snapshot behavior changed. No new dependency, additional action, separate Execute endpoint, retry/rollback, external delivery, WebSocket, queue, worker, scheduler, Redis, Admin Users UI, Evaluation UI, or M8 PR7 work was added.

### M8 PR7 — E2E, Security Hardening & Completion

Branch:

```text
feature/m8-e2e-security-completion
```

Status: implementation- and verification-complete; not merged.

Goal: close Milestone 8 by automating the real governed requester-to-approver workflow, enforcing PostgreSQL/RLS/action security gates in CI, mapping the required security cases to exact tests, and fixing only defects exposed by those release gates.

In scope:

- an isolated disposable PostgreSQL E2E preparation path that gives Demo Analyst the exact Finance scope without changing normal seed behavior or production permissions
- a release-blocking Manager → Analyst reclaim workflow through Ask Data, preview, submission, approval and synchronous execution, Audit, notifications, and a governed post-execution read
- a release-blocking negative Demo User flow with a valid-CSRF direct action-preview denial and persistence verification
- preservation and narrow extension of the existing Admin Audit/export browser smoke
- an exact tracked matrix for the 20 action cases, the broader 30 security cases, export, card refresh, LLM exposure, unsafe SQL, role-aware rendering, and the new browser flows
- separate PostgreSQL 16 and isolated M8 Playwright CI release gates with safe database identities and retained failure artifacts
- full backend, PostgreSQL, frontend, browser, migration, accessibility, responsive, cleanup, and manual-review verification

Guardrails:

- This is release hardening, not a feature PR. Existing backend authorization, effective permissions, exact scopes, CSRF, RLS, runtime roles, action policy, revalidation, execution, audit writing, notification recipients, and public contracts remain authoritative.
- The E2E scope preparation is PostgreSQL-only, explicitly destructive-test opted in, local/CI endpoint validated, idempotent, and restricted to a disposable database whose name contains a safe test/dev/e2e marker. It must refuse the normal application database and unsafe or ambiguous URLs.
- The state-changing primary browser flow uses its own freshly migrated and seeded database. It cannot retry against already-mutated targets or depend on test order.
- Existing strong tests are mapped rather than duplicated. New tests are added only for missing release evidence or defects directly exposed by a required gate.
- PR7 adds no schema or migration and does not change normal small/medium seed profiles, permission catalogs, role mappings, RLS policies, action eligibility, lifecycle behavior, notification delivery, or product capabilities.
- Do not add action types, a separate Execute endpoint, retries or rollback actions, background infrastructure, polling/realtime/external notification delivery, Admin Users or Evaluation UI, real LLM behavior, Supabase Auth, or next-milestone work.
- Milestone 8 may be marked complete only after every documented PR7 release gate passes on the final committed HEAD and task-owned resources are removed.

Delivered:

- A PostgreSQL-only E2E preparation guard requires explicit disposable opt-in, a loopback endpoint, a test/dev/e2e database marker, canonical separation from the normal application database, and no endpoint query overrides. It idempotently grants Demo Analyst exact Finance manage scope and stabilizes only the disposable workflow's time-sensitive service-account row; normal seed profiles are unchanged.
- The isolated primary Chromium flow automates Manager Ask Data → deterministic reclaim preview → submission → real logout → exact-scope Analyst review → synchronous approve-and-execute → Audit → requester/approver notifications → governed post-execution zero-row read. It asserts one submission, exact pending/unread totals, terminal state, two mutations, safe rendering, 390px layout, both themes, Escape/focus restoration, and no page/console errors.
- The negative User flow proves approved-template access without action suggestion or protected navigation, sends a direct preview request with a real current CSRF token, receives `403 FORBIDDEN`, and compares action, approval, audit, and notification persistence counts before and after.
- The tracked `docs/security/m8-release-test-matrix.md` maps the exact 20 action cases and broader 30 security requirements. Narrow missing evidence was added for Analyst device RLS, Analyst/Admin dashboard detail, and LLM exclusion of approval reasons, security-event descriptions, and application audit tables.
- CI now has a dedicated PostgreSQL 16 security job and a separate freshly migrated/seeded M8 primary E2E job. The PostgreSQL job runs the exact 20-case suite by name, runs the remaining complete backend suite, emits JUnit reports, and fails if either group skips a test.
- The only product fix removes an unnecessary requester-only Action detail fetch after an approval becomes terminal, while clearing stale preview timestamps and preserving the approval response as authoritative.

Final verification passed 14 E2E-database safety tests, the exact 20-case action suite plus two concurrency cases, 756 default backend tests with 151 expected PostgreSQL-only skips, all 907 disposable-PostgreSQL backend tests with no skips, 247 frontend tests, both TypeScript checks, the production build, seven general Chromium flows, and two isolated M8 primary/negative flows. A fresh PostgreSQL 16 cluster upgraded through `0010_disable_inactive_user`; Alembic current and no-diff checks passed, and no migration was added.

The final **Manual M8 PR7 release review — not a CodeRabbit result** found 0 Critical, 0 Major, and 4 actionable Minor issues. All were fixed: terminal approval reload no longer makes a requester-only fetch, time-relative seed drift is stabilized only in the disposable E2E database, the Admin export smoke uses the persisted `csv_export` contract, and PostgreSQL CI explicitly fails on skips. The repeated review found no remaining actionable issue.

No schema, migration, normal seed, permission, role mapping, RLS, runtime-role, action policy, lifecycle, execution, audit-writing, notification-recipient, or public API contract changed. The intentional M8 limits remain: only `reclaim_unused_license` and `disable_inactive_user` exist; execution is synchronous; notifications are database-only; there is no automatic retry or rollback action, queue, worker, scheduler, Redis, WebSocket, or external delivery; and operational intervention remains necessary if both execution and separate failure persistence fail. Milestone 8 is complete, and the next milestone has not started.
