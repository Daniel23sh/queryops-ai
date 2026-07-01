# QueryOps AI

QueryOps AI is planned as a governed conversational data workspace that will let users query structured business data in natural language, save insights as dashboards, and execute controlled operational actions through approval and audit workflows.

The project is being built to demonstrate how AI can be used not only to generate SQL, but also to support safe data exploration, reusable insights, permission-aware workflows, and auditable operational actions.

## Overview

Modern organizations often have valuable structured data stored in databases, but many business users cannot access it directly without help from analysts, developers, or IT teams.

QueryOps AI is designed to solve this with a controlled interface where users will be able to:

* ask questions about structured data in natural language
* receive SQL-backed results
* view explanations and assumptions
* save useful results as dashboard cards
* explore dashboards by role and department
* request operational actions based on query results
* route sensitive actions through approval flows
* keep a complete audit trail of important operations

The system is designed as a generic platform. The first implementation domain is IT Operations, but the core architecture should support additional domains in the future.

## First Domain: IT Operations

The first domain pack focuses on IT Operations data.

It uses synthetic but realistic operational data, including:

* departments
* directory users
* login events
* licenses
* license assignments
* devices
* software installs
* support tickets
* groups
* user group memberships
* security events
* IT audit events

Example questions the product should support:

* Which users have not logged in for more than 90 days and still have paid licenses?
* How many unused licenses exist by department?
* Which privileged users are inactive?
* Which devices are non-compliant or have outdated software?
* How many open support tickets exist by department and priority?
* Which terminated employees still have active accounts or assigned devices?

The IT Operations domain is only the first domain pack. Domain-specific tables, queries, dashboards, and actions should remain separate from the generic core engine.

## Core Product Flow

The intended product flow is:

```txt
Natural language question
→ safe SQL generation
→ SQL validation
→ scoped database execution
→ explained result
→ saved insight or dashboard card
→ suggested operational action
→ action preview
→ approval
→ execution
→ audit log
```

This makes QueryOps AI more than a text-to-SQL demo. It is designed as a governed operational data product.

## Main Capabilities

Planned V1 capabilities include:

* authentication and user onboarding
* role-based permissions
* natural-language data queries
* predefined query templates
* SQL generation and validation
* scoped query execution
* PostgreSQL Row-Level Security
* query history
* saved cards
* dashboard catalog
* personal and department dashboards
* controlled CSV export
* action recommendations
* action preview
* approval workflow
* notifications
* audit logs
* evaluation and testing screens

## User Roles

QueryOps AI is planned around four main roles.

### User

A regular user with limited read-only access.

Users can view approved dashboards, use approved templates, and access only the data they are allowed to see.

### Manager

A department-level business user.

Managers can ask natural-language questions about their department, view business-level insights, and create personal dashboards. They do not see raw SQL.

### Analyst

A technical department user.

Analysts can ask questions, view generated SQL, inspect query details, create department-level dashboard cards, and approve limited department actions according to policy.

### Admin

A global administrator.

Admins can manage users, approve role upgrades, access global data, manage global dashboards, approve sensitive actions, and view full audit and evaluation data.

## Architecture

QueryOps AI is planned as a monorepo with a separate frontend, backend, and database layer.

```txt
User Browser
→ React Frontend
→ FastAPI Backend
→ Auth and Permission Layer
→ Query Engine / Action Engine
→ PostgreSQL with RLS
→ Response Formatter
→ Dashboard / Tables / Charts
```

The frontend never communicates directly with the database or the LLM provider. All sensitive operations go through the backend, where authorization, validation, policy checks, and audit logging are enforced.

## Planned Tech Stack

### Frontend

* React
* TypeScript
* Vite
* Tailwind CSS
* shadcn/ui
* Recharts
* dnd-kit

### Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy 2
* Alembic
* Pytest

### Database

* PostgreSQL
* Row-Level Security
* Alembic migrations
* deterministic synthetic seed data

### Authentication

Planned authentication modes:

* production-like mode using Supabase Auth with Google OAuth
* local demo mode using seeded demo users

Supabase is planned to handle external identity only. QueryOps AI manages its own application users, roles, departments, permissions, and approval policies.

### AI Layer

The backend should use an LLM provider abstraction.

The LLM should not execute SQL directly and should never perform database mutations. Any generated SQL must pass backend validation before execution.

Operational actions are executed only by deterministic backend logic after preview, policy checks, approval, and audit logging.

## Planned Repository Structure

```txt
queryops-ai/
  backend/
    app/
    tests/
    pyproject.toml

  frontend/
    src/
    package.json

  docs/
    planning/        # local/private planning documents, ignored by Git

  README.md
  PROJECT_PLAN.md
  AGENTS.md
  docker-compose.yml
  .env.example
  .gitignore
```

## Local Planning Documents

The full planning documents may exist locally under:

```txt
docs/planning/
```

These files are intentionally ignored by Git and are used as private implementation context when working with a local development agent.

Expected local planning files:

```txt
01-product-brief.md
02-mvp-prd.md
03-technical-architecture.md
04-it-operations-domain-pack.md
05-security-permissions-matrix.md
06-actions-approvals-audit.md
07-api-contract.md
08-ui-flows-wireframes.md
09-evaluation-testing-plan.md
10-development-milestones.md
```

The repository should remain usable without committing these private planning documents.

## Security Model

Security is a core part of the product design.

The planned security model includes:

* backend-managed permissions
* role-based and permission-based access control
* PostgreSQL Row-Level Security
* safe SQL validation
* restricted SQL visibility by role
* scoped query execution
* controlled CSV export
* action approval policies
* prevention of self-approval where required
* audit logging for sensitive operations
* limited LLM data exposure

The system should not rely on frontend visibility rules alone. The backend and database must enforce the actual access rules.

## Action and Approval Model

QueryOps AI is designed to support controlled operational actions.

Example V1 actions for the IT Operations domain:

* reclaim unused license
* disable inactive user

Actions follow a governed lifecycle:

```txt
suggested
→ preview
→ submitted for approval
→ approved or rejected
→ executed
→ audited
```

The LLM may suggest an action type, but it does not choose final records, approve changes, or mutate the database. The backend calculates the preview, checks eligibility, enforces policy, executes the operation, and writes audit logs.

## Evaluation and Testing

The project should include evaluation and testing for both regular software behavior and AI-assisted behavior.

Planned testing areas:

* backend API tests
* permission tests
* PostgreSQL RLS tests
* SQL validation tests
* query execution tests
* action authorization tests
* approval workflow tests
* audit tests
* CSV export tests
* frontend role-based rendering tests
* end-to-end demo flow tests
* mock LLM provider tests
* real LLM evaluation outside regular CI

Security-related tests should be treated as release-blocking.

## Local Development

Local development setup will use Docker Compose.

Copy the example environment file if you want local overrides:

```bash
cp .env.example .env
```

Start the local development stack:

```bash
docker compose up --build
```

This starts:

* PostgreSQL database
* FastAPI backend
* React frontend

Default local URLs:

* Frontend: `http://localhost:5173`
* Backend health endpoint: `http://localhost:8000/health`
* PostgreSQL: `localhost:5432`

PostgreSQL is included for the local development environment. The current backend includes the database foundation, deterministic IT Operations seed data, and local demo auth session endpoints. Query engine behavior, RLS policies, dashboards, actions, approvals, and audit behavior remain planned for later milestones.

Stop the stack:

```bash
docker compose down
```

Remove the local PostgreSQL volume only when you intentionally want to reset local database state:

```bash
docker compose down -v
```

### Backend

The backend skeleton can be run locally without Docker with:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run backend tests:

```bash
pytest
```

Run Alembic commands from the host with PostgreSQL running:

```bash
export DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops
alembic current
alembic upgrade head
```

When running inside Docker Compose, the backend uses the `postgres` service hostname from `DATABASE_URL`.

Seed deterministic development data after migrations have been applied:

```bash
docker compose up -d postgres
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_it_operations.py --profile small --reset
.venv/bin/python scripts/seed_it_operations.py --profile medium --reset
```

The seed script is development-only and deterministic. Supported profiles are `small` for fast local or CI-style checks and `medium` for demo-scale local data. The `--reset` flag deletes seeded rows from the product and IT Operations tables before reseeding; it does not drop tables or modify Alembic migration state.

Local demo auth uses seeded users through `POST /api/v1/demo/login`, then hydrates the current user with `GET /api/v1/auth/me`. Login sets a signed, expiring httpOnly `qo_session` cookie and a readable `qo_csrf` cookie; state-changing authenticated requests such as `POST /api/v1/auth/logout` must send `X-CSRF-Token`.

### Frontend

The frontend skeleton can be run locally without Docker with:

```bash
cd frontend
npm install
npm run dev
```

Build and test commands:

```bash
npm run build
npm test
```

The frontend auth client calls the backend at `http://localhost:8000` by default.
Override it with `VITE_API_BASE_URL` if needed.

## Verification

### Backend

```bash
cd backend
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

### Frontend

```bash
cd frontend
npm install
npm test
npm run build
```

### Docker Compose

With Docker Desktop or another Docker daemon running:

```bash
cp .env.example .env
docker compose config
docker compose up --build
```

## Environment Variables

A `.env.example` file should document all required environment variables.

Example planned variables:

```env
AUTH_MODE=demo
SESSION_SECRET_KEY=queryops-local-session-secret
SESSION_COOKIE_SECURE=false
SESSION_MAX_AGE_SECONDS=28800
POSTGRES_DB=queryops
POSTGRES_USER=queryops
POSTGRES_PASSWORD=queryops
POSTGRES_PORT=5432
BACKEND_PORT=8000
FRONTEND_PORT=5173
DATABASE_URL=postgresql+psycopg://queryops:queryops@postgres:5432/queryops
VITE_API_BASE_URL=http://localhost:8000
```

Real secrets must never be committed to Git.

## Project Goals

QueryOps AI is intended to be a portfolio-grade software project that demonstrates:

* practical AI product design
* backend architecture
* database modeling
* permission-aware data access
* secure SQL execution
* action approval workflows
* auditability
* synthetic data generation
* evaluation methodology
* clean frontend dashboards
* Docker-based local development
* strong documentation and incremental delivery

## Current Status

Milestone 0 foundation work, Milestone 1 database/seed work, Milestone 2 auth/users/roles/permissions work, and Milestone 2.5 Access Context Foundation are complete.

Implemented foundation functionality includes:

* FastAPI backend skeleton with `GET /health`
* React + TypeScript + Vite frontend shell with backend health check
* Docker Compose setup for PostgreSQL, backend, and frontend
* `.env.example` with safe local placeholders
* basic backend and frontend tests
* initial GitHub Actions CI workflow
* SQLAlchemy and Alembic database foundation
* product and IT Operations domain schema
* deterministic IT Operations seed profiles and seed tests
* local demo auth session endpoints with CSRF protection and session expiration
* role and permission mapping with role upgrade request flow
* Access Context Foundation with access scopes, data resources, and simple access decisions

Current active planning target:

```txt
Post-Milestone 2.5 Hardening — Access Context Foundation
```

This branch hardens the merged Milestone 2.5 access-context foundation. RLS policies, Query Engine, dashboards, actions, approvals, CSV export behavior, and real LLM calls remain planned for later milestones.

## License

No license has been selected yet.
