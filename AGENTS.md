# QueryOps AI — Agent Instructions

These instructions contain durable, repository-specific rules. Current status and approved work belong only in `PROJECT_PLAN.md`; completed work belongs in `docs/history/development-history.md`.

## 1. Source of Truth

Apply `AGENTS.md` to every repository task. Load other sources only when they are relevant:

- Read `PROJECT_PLAN.md` when the task depends on current implementation scope, release state, blockers, or approved next work.
- Read `README.md` when supported behavior, setup, environment, repository structure, or verification commands are relevant.
- Read only the relevant local `docs/planning/` documents when detailed product, architecture, security, API, UX, or evaluation specifications are needed.

Trivial or local changes do not require loading unrelated project-state or planning context.

Explicit user instructions control the requested task. `PROJECT_PLAN.md` controls current implementation scope. Local planning documents are authoritative detailed specifications, but their historical milestone/status notes may be stale; verify current state from `main`, tracked release documents, and Git history. History documents are archaeological references, not active scope.

If sources materially conflict and the conflict cannot be resolved from the repository, stop and request a decision. Never infer a new milestone or implementation objective.

## 2. Local Planning Documents

`docs/planning/` is intentionally ignored and may exist only in a maintainer's workspace.

- Read the task-relevant documents when available.
- Do not stage or commit anything under `docs/planning/`.
- Do not modify those files unless the user explicitly requests it or a broken reference cannot otherwise be corrected.
- Do not copy large private sections into tracked documentation.

## 3. Scope and Change Control

- Implement only the user's request within the approved scope in `PROJECT_PLAN.md`.
- Treat an empty "Next Approved Work" section as a stop condition for new implementation.
- Preserve unrelated user changes and avoid unrelated refactors.
- Do not silently change product behavior, public contracts, authorization, persistent data, release policy, or product scope.
- Keep IT Operations as a domain pack; do not hard-code the generic Query or Action engines to one domain without an approved design change.

## 4. Architecture

- Keep the monorepo architecture: React, TypeScript, and Vite in `frontend/`; FastAPI and Python in `backend/`; PostgreSQL through SQLAlchemy 2 and Alembic; Docker Compose for the supported local stack.
- The frontend never talks directly to PostgreSQL or an LLM/provider. All data, provider, policy, and mutation paths go through the backend.
- Keep provider integration behind the existing abstraction and dependency seams.
- Keep seed data deterministic and synthetic. Never introduce production identities or sensitive data into seed or evaluation fixtures.

## 5. Authorization and Data Boundaries

- Backend authorization and PostgreSQL policy are authoritative. Frontend capability checks are usability controls only.
- Authorize from current effective permission keys and `UserAccessContext`, including exact assigned scopes. Do not substitute role-name checks for permission decisions.
- Authorize each resource independently and fail closed when identity, scope, resource metadata, persisted shapes, or policy context is missing or inconsistent.
- Never infer identity between `app_users` and `directory_users` from email, name, provider ID, or other matching attributes.
- Use explicit, role-appropriate response projections. Do not expose SQL, rows, prompts, provider payloads, secrets, raw database errors, stack traces, hidden-scope totals, permission internals, or arbitrary persisted JSON without an existing explicit contract and permission.
- Product UI uses **Scope** as the general governance term. **Department** remains valid for the IT Operations model, compatibility APIs, and existing permission names.

## 6. Query and LLM Safety

- Approved templates remain deterministic and provider-free.
- Free queries use the provider only to produce the structured plan defined by the current contract. The backend validates the plan and renders SQL deterministically.
- Treat every LLM/provider output and all backend-rendered SQL as untrusted.
- Execute only validator-sanitized, single-statement, read-only SQL after resource authorization and semantic conformance checks.
- Query execution must use the non-owner, read-only `queryops_query_runtime` role, transaction-local RLS context, bounded limits/timeouts, and PostgreSQL RLS.
- The LLM context must be an allowlisted projection of authorized schema and approved semantics. Never send database rows, user identities, raw scope keys, permissions, credentials, evaluation baselines or answers, prior SQL, protected resources, or action targets.
- Do not add provider SQL, direct business-logic provider calls, repair calls, fallback providers, or direct LLM database mutations without an explicitly approved architecture change.
- Mock is the development and CI default. Never make a real, billable provider request without explicit operator authorization covering the exact model and allowed run count.

## 7. Derived Data and Evaluation

- Dashboard-card refresh and CSV export must reauthorize and re-execute under the current viewer's access context; never reuse the creator's authority.
- Preserve SQL revalidation, the query runtime role, read-only limits, RLS, CSV formula-injection protection, safe filenames, and successful export audit behavior.
- Do not persist raw query-result rows in dashboard config/layout, browser storage, URLs, or another snapshot store.
- Evaluation metrics and readiness surfaces are read-only. They must never start evaluation, invoke a provider, execute SQL, or infer quality from unrelated product tables.
- Recompute scoped evaluation totals only from visible validated results. Never expose inaccessible run existence, hidden-scope aggregates, evaluator baselines, or internal evidence through API or UI projections.

## 8. Action Safety

- The LLM may suggest only a registered action type; it must never select mutation targets or produce mutation SQL.
- Actions use explicit bounded selectors and deterministic backend handlers.
- Preserve preview, current-state revalidation, effective-permission and exact-scope policy checks, approval, idempotent execution, atomic audit/notification writes, and terminal-state protections.
- Domain writes must use the narrowly privileged non-owner `queryops_action_runtime` role with transaction-local actor/scope context and PostgreSQL RLS. Never reuse the read-only query role or an owner-session shortcut.
- Keep requester, approver, application-user, and directory-user identities distinct. Populate domain actor fields only with the correct identity type.
- Do not persist raw query rows, provider content, unrestricted snapshots, SQL, secrets, or internal failure details in action, audit, or notification payloads.

## 9. Database and Persistence

- Use SQLAlchemy 2 and Alembic for schema changes; keep models and migrations aligned.
- Preserve non-owner runtime roles, least-privilege grants, `NOLOGIN`, `NOINHERIT`, `NOBYPASSRLS`, transaction-local context, and RLS policies unless an approved task explicitly changes them.
- Never use the normal application database for destructive, reset, concurrency, migration round-trip, or state-changing release tests. Require an explicitly disposable database with guard checks.
- Never reset, reseed, downgrade, or remove a user database or service as a routine validation step.
- Do not commit secrets, local environment files, generated build artifacts, provider payloads, or raw evaluation data.

## 10. Documentation and Validation

- Keep `PROJECT_PLAN.md` concise and limited to current/next work; move completed narratives and evidence to `docs/history/development-history.md`.
- Update `README.md` only when supported behavior, setup, environment variables, repository structure, or verification commands change.
- Update tracked security, evaluation, QA, or API documents when their contracts or evidence change; do not duplicate their full content in instruction files.
- Add focused regression coverage for behavior changes, especially authorization, RLS, SQL safety, actions, evaluation, migrations, and disclosure boundaries.
- Use PostgreSQL-backed tests for behavior that depends on roles, grants, RLS, locking, concurrency, or database semantics. SQLite-only evidence is insufficient for those contracts.
- Before finishing, review the diff, run validation proportional to the change, verify Markdown references when documentation changes, and confirm ignored planning files are neither tracked nor staged.
