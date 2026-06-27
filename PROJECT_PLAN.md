# QueryOps AI — Project Plan

## 1. Current Development Target

The current active target is:

`Milestone 0 — Project Setup & Development Environment`

This phase is foundation only. The goal is to establish a clean local development environment, repository structure, backend skeleton, frontend skeleton, Docker Compose setup, and basic verification hooks. It is not the phase for real product feature implementation.

Milestone 0 foundation work is now ready for review and merge. Do not begin Milestone 1 implementation until Milestone 0 has been verified and accepted.

Do not start implementing QueryOps product behavior yet. Product schema, auth flows, permissions, natural-language querying, dashboards, actions, approvals, audit logs, and evaluation belong to later milestones.

## 2. Product Summary

QueryOps AI is a governed conversational data workspace. It lets users ask natural-language questions over structured data, receive safe SQL-backed results, save useful results as cards and dashboards, and eventually trigger controlled operational actions.

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
- Supabase Auth with Google OAuth is planned later.
- Use demo auth first for local development and early milestones.
- Store internal QueryOps roles, departments, and permissions in local PostgreSQL.
- PostgreSQL Row-Level Security is required in later milestones.
- Use an LLM provider abstraction.
- Do not call an LLM directly from business logic.
- Do not allow direct LLM database mutations.
- Natural-language SQL must be read-only and validated before execution.
- Actions must use deterministic backend logic.
- Actions require preview, policy check, approval, execution, and audit.
- IT Operations is the first domain pack, not a product hard-coding target.
- The frontend never talks directly to PostgreSQL or an LLM.
- The backend is the source of truth for permissions and policy enforcement.

## 5. Milestone 0 Scope

Milestone 0 includes only project foundation work:

- Repository structure.
- Backend skeleton.
- Frontend skeleton.
- Docker Compose setup.
- PostgreSQL container.
- `.env.example`.
- FastAPI health endpoint.
- Basic frontend shell.
- Frontend/backend connectivity check if practical.
- Basic backend test placeholder.
- Basic frontend test placeholder.
- Initial lint, typecheck, and test scripts where practical.
- Basic CI structure if appropriate.
- README updates with real local run commands.
- Optional migration-tool placeholder only if useful for setup; no product/domain migrations yet.

The backend should be able to start. The frontend should be able to start. Local setup should be boring, repeatable, and easy to verify.

## 6. Explicitly Out of Scope for Milestone 0

Do not implement the following in Milestone 0:

- Full database schema.
- Alembic migrations for product/domain tables.
- Synthetic seed data.
- Supabase Auth.
- Google OAuth.
- Real user management.
- Roles and permissions logic.
- RLS policies.
- Natural language to SQL.
- Real LLM provider calls.
- Dashboards.
- Cards.
- Query history.
- CSV export.
- Actions.
- Approvals.
- Notifications.
- Audit logs.
- Evaluation engine.
- Production deployment.

If a future feature needs a placeholder, keep it inert and clearly non-functional.

## 7. Target Repository Structure

Expected structure after Milestone 0:

```text
queryops-ai/
  backend/
    app/
      __init__.py
      main.py
      api/
      core/
    tests/
      test_health.py
    pyproject.toml

  frontend/
    src/
      main.tsx
      App.tsx
    package.json
    vite.config.ts
    tsconfig.json

  docs/
    planning/        # local/private, ignored by Git

  README.md
  PROJECT_PLAN.md
  AGENTS.md
  docker-compose.yml
  .env.example
  .gitignore
```

Adjust exact file placement only when the repository has already established a reasonable convention. Keep the Milestone 0 structure simple.

## 8. Backend Foundation Requirements

The minimal backend for Milestone 0 is:

- FastAPI application.
- `GET /health`.
- JSON response:

```json
{ "status": "ok", "service": "queryops-backend" }
```

- Test for the health endpoint.
- No real business logic.
- No real authentication.
- No real permissions.
- No real database schema.
- No real LLM integration.

The backend may include configuration plumbing and a PostgreSQL connection check if practical, but it must not introduce product tables or domain behavior.

## 9. Frontend Foundation Requirements

The minimal frontend for Milestone 0 is:

- React, TypeScript, and Vite.
- Simple app shell.
- Project name displayed.
- Optional backend health check display if practical.
- Basic test placeholder.
- No real dashboard UI.
- No real authentication UI.
- No role-specific navigation.
- No action, approval, audit, query, or evaluation screens.

The frontend should prove the toolchain works without pretending future product workflows are implemented.

## 10. Docker and Environment Requirements

Local development should use Docker Compose.

Expected services:

- `postgres` service in Milestone 0.
- `backend` service eventually.
- `frontend` service eventually.

Milestone 0 should include `.env.example` with safe placeholder values only. Do not commit real secrets.

Expected placeholder variables:

```env
AUTH_MODE=demo
POSTGRES_DB=queryops
POSTGRES_USER=queryops
POSTGRES_PASSWORD=queryops
DATABASE_URL=postgresql://queryops:queryops@postgres:5432/queryops
```

Future environment variables such as Supabase settings or LLM API keys may be listed as empty placeholders only when needed, but real values must never be committed.

## 11. Development Rules for Agents

Agents working in this repository must:

- Read this file before coding.
- Use local `docs/planning/` when available.
- Implement only the requested milestone or task.
- Keep Milestone 0 limited to foundation work.
- Do not add unplanned scope.
- Keep changes small and reviewable.
- Update README when commands change.
- Do not commit ignored planning docs.
- Do not commit secrets.
- Do not introduce real LLM calls before requested.
- Do not implement future milestones early.
- Do not create product/domain tables during Milestone 0.
- Do not add auth, permissions, RLS, query engine, dashboards, actions, approvals, audit, or evaluation until their milestones.
- Prefer boring, maintainable structure over clever abstractions.

If a task request conflicts with this file, clarify the intended milestone before implementing broad product behavior.

## 12. Suggested Commit Sequence for Milestone 0

Intended commits:

1. Ignore local planning documents.
2. Add initial project README.
3. Add project plan.
4. Add agent instructions.
5. Add backend skeleton.
6. Add frontend skeleton.
7. Add Docker Compose and environment example.
8. Add initial CI and test placeholders.

Milestone 0 foundation commit sequence is complete through the initial CI and test placeholders.

## 13. Milestone 0 Acceptance Criteria

Milestone 0 is complete when:

- Backend starts.
- Frontend starts.
- `GET /health` works.
- Docker Compose starts local services or limitations are clearly documented.
- `.env.example` exists with safe placeholders.
- README has accurate local run commands.
- Basic backend tests or placeholders exist.
- Basic frontend tests or placeholders exist.
- Initial lint/typecheck/test scripts exist where practical.
- No private planning docs are committed.
- `git status` is clean after commit.

Milestone 0 should leave the repository ready for Milestone 1 without smuggling in Milestone 1 implementation.

## 14. Next Milestone

After Milestone 0, the next target is:

`Milestone 1 — Database Schema & IT Operations Seed`

Milestone 1 must not start until Milestone 0 is complete and verified.
