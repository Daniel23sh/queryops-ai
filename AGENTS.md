# QueryOps AI — Agent Instructions

These instructions apply to all AI coding agents working in this repository.

## 1. Read Before Coding

Before making code changes, always read:

1. `README.md`
2. `PROJECT_PLAN.md`
3. Local planning documents under `docs/planning/`, if available

The `docs/planning/` directory is intentionally ignored by Git. It may exist only in the local workspace and should be used as private implementation context when available.

Do not commit files from `docs/planning/`.

## 2. Current Active Target

The current active development target is defined in PROJECT_PLAN.md.

```txt
Agents must always follow the active milestone scope in PROJECT_PLAN.md and must not implement future milestone work unless explicitly requested.
```

Milestone 0 is foundation work only.

Do not implement real product features during Milestone 0.

## 3. Milestone 0 Scope

Allowed work during Milestone 0:

* repository structure
* backend skeleton
* frontend skeleton
* Docker Compose setup
* PostgreSQL development container
* `.env.example`
* FastAPI health endpoint
* basic frontend shell
* backend/frontend connectivity check if practical
* basic backend test placeholder
* basic frontend test placeholder
* basic lint/typecheck/test scripts where practical
* README updates with real local development commands

## 4. Explicitly Out of Scope

Do not implement these unless specifically requested in a later milestone:

* full database schema
* Alembic migrations for product/domain tables
* synthetic seed data
* Supabase Auth
* Google OAuth
* real user management
* roles and permissions logic
* PostgreSQL RLS policies
* natural-language-to-SQL pipeline
* real LLM provider calls
* dashboards
* cards
* query history
* CSV export
* actions
* approvals
* notifications
* audit logs
* evaluation engine
* production deployment

If a future task appears to require one of these, stop and explain that it belongs to a later milestone.

## 5. Product Direction

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

## 6. Architecture Decisions

Follow these locked decisions unless explicitly changed by the user:

* monorepo
* React + TypeScript + Vite frontend
* FastAPI + Python backend
* PostgreSQL database
* Docker Compose for local development
* demo auth before real Supabase Auth
* Supabase Auth planned later for identity only
* QueryOps manages its own roles, departments, and permissions
* PostgreSQL RLS required in later milestones
* LLM provider abstraction
* no direct LLM database mutations
* actions must be executed by deterministic backend logic
* actions require preview, policy check, approval, execution, and audit

## 7. Coding Rules

Use simple, maintainable structure.

Prefer boring and clear code over clever abstractions.

Keep changes small and focused.

Do not introduce unnecessary dependencies.

Do not create future-proof abstractions before they are needed.

Do not silently change product scope.

Do not rewrite unrelated files.

Do not modify ignored planning documents unless explicitly asked.

Do not commit secrets.

Do not commit generated build artifacts.

Do not commit local environment files.

## 8. Documentation Rules

Update `README.md` when:

* setup commands change
* Docker commands change
* backend run commands change
* frontend run commands change
* environment variables change
* repository structure changes

Update `PROJECT_PLAN.md` only when the development plan or active milestone changes.

Keep `README.md` focused on the project.

Keep `PROJECT_PLAN.md` focused on implementation control.

Keep `AGENTS.md` focused on agent behavior rules.

## 9. Testing Rules

When adding backend code, add or update backend tests when practical.

When adding frontend code, add or update frontend tests when practical.

For Milestone 0, simple health-check tests or placeholders are enough.

Do not add complex E2E tests before the basic app structure exists.

Security-related behavior in later milestones must have tests.

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

Recommended Milestone 0 commit sequence:

```txt
1. Ignore local planning documents
2. Add initial project README
3. Add project plan
4. Add agent instructions
5. Add backend skeleton
6. Add frontend skeleton
7. Add Docker Compose and environment example
8. Add initial CI and test placeholders
```

Current Milestone 0 status:

```txt
Foundation work is ready for review and merge.
```

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

## 12. If Unsure

If implementation details are unclear:

1. Check `PROJECT_PLAN.md`
2. Check local `docs/planning/`
3. Choose the smallest implementation that satisfies the current milestone
4. Avoid adding future milestone features
5. Document assumptions in the final response
