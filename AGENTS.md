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

## 2. Active Milestone Source of Truth

The current active development target is defined in `PROJECT_PLAN.md`.

```txt
Agents must follow the active milestone scope in PROJECT_PLAN.md and must not implement future milestone work unless explicitly requested.
```

If a task is outside the active milestone in `PROJECT_PLAN.md`, stop and report the mismatch instead of implementing it.

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

The active milestone is defined in `PROJECT_PLAN.md`.

At the time this file was updated, the active target is:

```txt
Milestone 2 — Auth, Users, Roles & Permissions
```

Milestone 2 may include demo authentication, backend session handling, CSRF foundation, app users, roles, permissions, role upgrade workflow, and tests for those behaviors.

Milestone 2 PR 1 must stay limited to backend auth/session foundation. It must not implement runtime permission enforcement, PostgreSQL RLS policies, natural-language query pipeline, real LLM calls, dashboards UI, actions, approvals, notifications behavior, audit behavior, evaluation engine behavior, or production deployment.

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
