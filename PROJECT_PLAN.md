# QueryOps AI — Project Plan

## 1. Current Development Status

The current milestone status is:

`Milestone 5 PR1 — M4 Query Backend Compliance` is active.

Milestone 0 foundation work, Milestone 1 database and IT Operations seed work, Milestone 2 auth/users/roles/permissions work, Milestone 2.5 Access Context Foundation, Post-Milestone 2.5 hardening, Milestone 3 RLS & Security Foundation, and Milestone 4 Query Engine Backend are complete.

Milestone 5 has started with the first backend compliance PR only. Do not start Ask Data UI, dashboards, dashboard cards, CSV export, actions, approvals, notifications, or frontend work until the backend compliance PR is complete, tested, and merged.

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

Milestone 5 PR1 is active on branch `feature/m5-fix-m4-query-backend-compliance`. This branch closes the remaining Milestone 4 backend compliance gaps before any frontend Ask Data UI work begins. Do not start frontend Ask Data work until the backend compliance PR is complete, tested, and merged.

Milestone 5 PR1 scope:

- add `POST /api/v1/queries/{query_run_id}/clarify`
- add `GET /api/v1/queries/scope-history`
- add `GET /api/v1/queries/department-history` as a V1 compatibility alias
- add deterministic self-correction in the backend query engine
- expose safe query metadata needed by the future Ask Data UI

Milestone 5 PR1 must not add frontend Ask Data UI, a real LLM provider, dashboards, CSV export, actions, approvals, or notifications.

Items still out of scope and reserved for future milestones:

- dashboards UI
- dashboard cards behavior
- CSV export
- actions behavior
- approvals behavior
- notifications behavior
- real external LLM calls
- Supabase Auth
- frontend Ask Data UI
- Full ABAC
- ReBAC
- policy builder UI
- dynamic policy engine
- masking
- tenant/project/region governance

Milestone 5 or later will handle dashboards, UI, actions, and approvals unless explicitly requested.

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

`Milestone 4 — Query Engine Backend`

Milestone 4 is complete. It delivered backend Query Engine foundations only: domain pack loading, query templates, mock LLM generation, schema context, SQL validation, runtime RLS role hardening, scoped read-only execution with PostgreSQL RLS, query run APIs, `QueryRun` persistence, PostgreSQL-backed tests, and security regression/evaluation tests.

Milestone 5 PR1 is active for backend/API compliance only. Milestone 5 later PRs remain responsible for Ask Data UI. Dashboards, dashboard cards, CSV export, actions, approvals, and notification behavior remain out of scope unless explicitly requested in a later milestone or PR.

## 15. Milestone 5 Implementation Plan

Milestone 5 PR1 is active. Use one branch per PR, do not include PR numbers in branch names, split every PR into checkpoints, and end each checkpoint with its own commit. Do not create one large commit for an entire PR.

The first Milestone 5 PR must close the remaining Milestone 4 backend compliance gaps and make the Query API ready for the Ask Data UI. Frontend Ask Data implementation must not begin until PR1 is complete, tested, and merged.

### PR1: M4 Query Backend Compliance

Branch:

```text
feature/m5-fix-m4-query-backend-compliance
```

Goal:

Close Milestone 4 backend compliance gaps and make the Query API ready for Milestone 5 UI.

Checkpoints:

1. Checkpoint 1.1 — Document the M4 backend compliance scope in `PROJECT_PLAN.md` or `AGENTS.md`.
   - Commit: `docs: document m4 backend compliance scope for m5`

2. Checkpoint 1.2 — Add `POST /api/v1/queries/{query_run_id}/clarify`.
   - Verify ownership of the original query run.
   - Reject invalid payloads.
   - Create a new `QueryRun`.
   - Store safe metadata linking it to the original query.
   - Commit: `feat(api): add query clarification endpoint`

3. Checkpoint 1.3 — Add `GET /api/v1/queries/scope-history` and `GET /api/v1/queries/department-history` as a V1 compatibility alias.
   - Use `UserAccessContext` and access scopes, not direct department authorization.
   - Hide SQL unless the viewer has `can_view_sql`.
   - Commit: `feat(api): add scope-aware query history endpoints`

4. Checkpoint 1.4 — Add deterministic self-correction support in `QueryEngineService`.
   - If generated SQL fails validation, allow one safe correction attempt using only safe validation metadata.
   - Do not add real LLM providers, external provider integrations, API keys, or API-key requirements.
   - Commit: `feat(query-engine): add deterministic self-correction flow`

5. Checkpoint 1.5 — Expose safe query metadata needed by Ask Data UI.
   - Include self-correction metadata when present.
   - Do not expose unsafe provider internals.
   - Commit: `fix(api): expose safe query metadata for ask data ui`

6. Checkpoint 1.6 — Add or update backend tests and documentation.
   - Run backend tests and PostgreSQL query/RLS tests where available.
   - Commit: `docs: mark m4 query backend cleanup complete`

### PR2: Ask Data API Clients

Branch:

```text
feature/m5-ask-data-api-clients
```

Goal:

Build frontend API clients and types for query templates and query runs.

Start only after PR1 is merged.

### PR3: Ask Data Shell

Branch:

```text
feature/m5-ask-data-shell
```

Goal:

Replace the Ask Data placeholder with a real split workspace layout.

Start only after PR1 is merged.

### PR4: Ask Data Query Integration

Branch:

```text
feature/m5-ask-data-query-integration
```

Goal:

Load templates, run template queries, run free queries by role, and render the result table, clarification, loading, error, and no-row states.

Start only after PR1 is merged.

### PR5: Ask Data Role Tabs and Tests

Branch:

```text
feature/m5-ask-data-role-tabs-tests
```

Goal:

Add the SQL tab for Analyst/Admin only, technical/corrections tab, role-based tests, query state tests, and final docs polish.

Start only after PR1 is merged.

### Milestone 5 Out of Scope

Do not include the following in Milestone 5 unless explicitly approved in a later scope update:

- dashboards/cards behavior
- CSV export
- action preview
- approvals
- notifications
- real LLM providers
- Supabase Auth
- full expansion to 36 templates / 40 evaluation cases unless handled in a separate Domain Pack PR
