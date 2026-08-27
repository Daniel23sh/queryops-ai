# QueryOps V1 Readiness Report

Policy: `queryops-v1-readiness-v1`

## Source state

- Verified source `main`: `c6691a204ccbb9eb007e2e0c6fe419c346745b13`
- PR6 merge: PR #41, `Feature/m9 v1 quality gates readiness`
- PR6 final feature commit: `ee681da738466031478d982d53d1b3d0ef40b75f`
- PR6 GitHub checks: Backend, PostgreSQL Security, Frontend, E2E, M8 Primary E2E, and V1 Deterministic Release Gates passed
- PR7 branch: `feature/m9-v1-release-validation-completion`
- PR7 base HEAD: `e9ee2ccae205549185c246ca3ca02794f0b2786e`
- PR7 runtime commit: not frozen
- Dataset: `it_operations_v1`, version `1`
- Dataset digest: `1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4`
- Semantic catalog: `it_operations_semantic_catalog`, version `3`
- Semantic catalog hash: `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`
- Evaluation environment: pending final PR7 manifest identity

Semantic catalog v3 provides primitive/composed directory-user concepts, canonical `active_human_users`, deterministic mandatory/optional semantic grounding, and a one-call structured `SemanticPlan` plus SQL contract. There is no repair or second provider call. The existing SQL safety validator remains the security boundary; SQLGlot semantic conformance is an additional correctness layer over final sanitized SQL before execution, and PostgreSQL RLS remains authoritative. Evaluation records classify generation, SQL-safety, semantic-conformance, execution, and scoring stages.

The `itops-medium-009` baseline correction is objectively justified by the established “non-compliant device” business term and deterministic template, which both define the posture as non-compliant status, missing/outdated antivirus, or disabled encryption. Runtime score improvement was not used as evidence.

## Live measurement

Not performed on the final PR7 runtime. No prior diagnostic or partial live run is accepted as V1 release evidence. Fresh authorization is required after the behavior-affecting runtime is frozen and all deterministic checks pass.

The release-validation smoke procedure uses frozen case `itops-easy-005`, an easy `free_query` success case with no template. Template-backed `itops-easy-001` is not accepted as provider validation because it can complete without an OpenAI call. A qualifying smoke must show at least one sanitized provider call, and the exact API model ID must be explicitly authorized before execution.

- Provider/model: not available
- Run ID: not available
- Completion: not available
- Gate values: not available
- Safe call/attempt/token/latency totals: not available

## Deterministic evidence

The current network-free PR7 implementation candidate has the following deterministic evidence:

- focused Text-to-SQL: 375 passed
- default backend: 1,100 passed, 156 expected PostgreSQL-only skips
- fresh disposable PostgreSQL 16 backend: 1,236 passed, zero failures and zero skips
- exact M8 action-security release suite: 20 passed
- frontend Vitest: 274 passed
- Ruff, Pyright with zero errors/warnings, ESLint, application TypeScript, Node/Vite TypeScript, and production build: passed
- Playwright: 12 general flows and two isolated M8 flows passed
- Docker Compose: backend and frontend up; PostgreSQL healthy
- Alembic: head `0010_disable_inactive_user`; check passed
- Codex Security scan `f7036ba0-9e86-40c4-9e2d-0177908bbc31`: completed across all 17 changed runtime/configuration surfaces with zero findings

These results support commit/freeze of the implementation candidate. They are not live-provider or manual-QA evidence and do not make V1 ready. The broad suites predate only the baseline-decision regression, documentation updates, security-scan finalization, and task-owned resource cleanup; focused post-change checks are recorded separately during final stabilization.

## Verdict

`incomplete`

PR7 implementation stabilization is prepared for commit/freeze, but release evidence is not complete. Milestone 9 and QueryOps AI V1 must not be marked complete until an immutable candidate is tested by an explicitly authorized qualifying OpenAI smoke/full 40-case evaluation and the complete manual QA checklist passes on that unchanged candidate.

This report contains no prompts, SQL, expected or actual rows, provider payloads, secrets, raw errors, database URLs, or evaluator baselines.
