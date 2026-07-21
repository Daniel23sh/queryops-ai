# QueryOps V1 Readiness Report

Policy: `queryops-v1-readiness-v1`

## Source state

- Verified `main`: `695be1358ea2fcd67fc2cd25c66e2281986dd99f`
- PR5 merge: PR #40, `Feature/m9 real llm evaluation`
- Dataset: `it_operations_v1`, version `1`
- Dataset digest: `158fe5dd8e758d1f8f6ba8f8a9c4ea26d7f2e89fa3cf9689286f0ae9ed5d162a`

## Live measurement

Not performed. No billable live OpenAI execution was authorized during this task, and no prior live OpenAI run has been accepted as V1 release evidence.

- Provider/model: not available
- Run ID: not available
- Completion: not available
- Gate values: not available
- Safe call/attempt/token/latency totals: not available

## Deterministic evidence

Local network-free evidence on the reviewed feature-branch HEAD:

- focused readiness, CLI, and Evaluation API: 98 passed
- default backend: 939 passed, 153 expected PostgreSQL-only skips
- fresh disposable PostgreSQL backend: 1,092 passed, zero skips
- exact M8 action-security release suite: 20 passed
- tracked broader 30-case security matrix: mapped tests passed within the full PostgreSQL suite
- frontend Vitest: 274 passed
- Ruff, scoped Pyright, Python compilation, ESLint, application TypeScript, Node/Vite TypeScript, and production build: passed
- fresh Alembic upgrade/current/check: head `0010_disable_inactive_user`, no new upgrade operations
- general Chromium flows: 12 passed, including five Evaluation role/responsive flows and the Admin restricted-export smoke
- isolated state-changing M8 primary flow and persistence-safe User negative flow: passed
- Docker Compose configuration/startup smoke: passed; the normal local stack was restored after disposable verification

CodeRabbit CLI `0.6.5` was installed but unauthenticated, so no CodeRabbit result is claimed. The final **Manual M9 PR6 security and release review — not a CodeRabbit result** found one Major fail-closed issue and three actionable Minor issues. The fixes made deterministic evidence explicit instead of default-passed, rejected unknown/contradictory frontend gate payloads as unavailable, added an Analyst-safe technical evidence identity without global gate values/usage/counts, and corrected stale milestone/threshold documentation. Focused affected verification was rerun successfully, with no remaining actionable finding.

## Verdict

`incomplete`

Implementation and deterministic verification are complete, but release evidence is not. Milestone 9 and QueryOps AI V1 must not be marked complete until a qualifying full 40/40 OpenAI run passes every real-provider gate and the manual QA checklist is completed.

This report contains no prompts, SQL, expected or actual rows, provider payloads, secrets, raw errors, database URLs, or evaluator baselines.
