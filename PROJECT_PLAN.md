# QueryOps AI — Project Plan

## 1. Current Development Target

The current active target is:

`Milestone 4 — Query Engine Backend`

Milestone 0 foundation work, Milestone 1 database and IT Operations seed work, Milestone 2 auth/users/roles/permissions work, Milestone 2.5 Access Context Foundation, Post-Milestone 2.5 hardening, and Milestone 3 RLS & Security Foundation are complete.

Milestone 4 implements the backend Query Engine foundation on top of the Milestone 3 RLS and Security Foundation. It must preserve the existing Access Context Foundation and RLS behavior while adding only backend query-engine capabilities.

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

Milestone 4 scope:

- Domain Pack Loader
- Query Templates API
- `LLMProvider` interface
- `MockLLMProvider`
- SQL generator wrapper
- Schema Context Builder
- SQL validator
- read-only scoped Query Executor
- Query Run API
- `QueryRun` persistence
- PostgreSQL/RLS query tests

Milestone 4 out of scope:

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

Milestone 5 or later will handle dashboards, UI, actions, and approvals unless explicitly requested. Milestone 4 must not add frontend Ask Data UI, dashboard behavior, action execution, approval behavior, or CSV export.

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

## 14. Active Milestone

The active product milestone is:

`Milestone 4 — Query Engine Backend`

Milestone 4 is active. It focuses on backend Query Engine foundations only: domain pack loading, query templates, mock LLM generation, schema context, SQL validation, scoped read-only execution with PostgreSQL RLS, query run APIs, and `QueryRun` persistence.

Milestone 5 or later remains responsible for Ask Data UI, dashboards, dashboard cards, CSV export, actions, approvals, and notification behavior unless explicitly requested.
