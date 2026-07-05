# QueryOps AI — Project Plan

## 1. Current Development Status

The current milestone status is:

`Milestone 6 — Dashboards, Cards & CSV Export` is active.

Active PR scope:

`M6 PR3 — CSV Export Backend` is active on branch `feature/m6-csv-export-backend`.

Milestone 0 foundation work, Milestone 1 database and IT Operations seed work, Milestone 2 auth/users/roles/permissions work, Milestone 2.5 Access Context Foundation, Post-Milestone 2.5 hardening, Milestone 3 RLS & Security Foundation, Milestone 4 Query Engine Backend, and Milestone 5 Ask Data UI/frontend redesign are complete.

Milestone 5 PR6 has been merged into `main`. M5 Ask Data and the M5 frontend redesign are complete. Milestone 6 is now active. M6 PR1 dashboards/cards backend foundation is complete and merged into `main`. M6 PR2 dashboard/card frontend UI is complete and merged into `main`.

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

Milestone 6 PR3 is active on branch `feature/m6-csv-export-backend`. The current checkpoint is CSV export backend foundation only: backend API skeleton, request validation, auth/CSRF protection, permission seed alignment, focused backend tests, and documentation status.

Explicitly out of scope for the current M6 PR3 checkpoint:

- actual CSV file generation
- full export execution
- export audit persistence
- frontend export UI
- card refresh execution
- drag-and-drop
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

Later Milestone 6 PRs may handle full CSV generation/execution, export audit persistence, frontend export UI, card refresh, and reordering. Later milestones will handle actions, approvals, notifications, real LLM/API-key support, and Supabase Auth unless explicitly requested.

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

`Milestone 5 PR6 — Tailwind UI Foundation & Full Frontend Redesign`

Milestone 5 PR6 is merged into `main`. It added the Tailwind foundation, light/dark mode, redesigned app shell/sidebar, redesigned Dashboard, focused Ask Data command workspace, light polish for remaining frontend pages, and final CSS/docs cleanup.

Milestone 5 Ask Data and the Milestone 5 frontend redesign are complete.

The active product milestone is:

`Milestone 6 — Dashboards, Cards & CSV Export`

The current PR is:

`M6 PR3 — CSV Export Backend`, active on branch `feature/m6-csv-export-backend`.

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

Prepare the first backend CSV export surface for query runs and saved cards without executing exports yet.

Status:

Active. The current checkpoint is CSV export backend foundation only.

Current checkpoint in scope:

- backend CSV export API skeleton
- strict request validation for export payloads
- authentication and CSRF protection
- minimal `can_export_results` permission seed alignment
- query-run ownership and succeeded-status checks
- card/dashboard visibility checks
- controlled not-implemented placeholder responses
- backend tests for auth, CSRF, payload validation, permission, ownership/status, visibility, and SQL non-exposure
- `PROJECT_PLAN.md` and `AGENTS.md` status updates

Out of scope for the current checkpoint:

- actual CSV file generation
- full export execution
- export audit persistence
- frontend export UI
- card refresh execution
- drag-and-drop
- actions
- approvals
- notifications
- real LLM/API-key support
- Supabase Auth
- Redis/background jobs
- domain pack expansion

Later M6 PR3 checkpoints may implement CSV generation, export-time policy/RLS enforcement, CSV injection sanitization, row limits, and export audit persistence.
