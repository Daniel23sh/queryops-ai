# QueryOps V1 Readiness Report

Policy: `queryops-v1-readiness-v1`

## Source state

- Verified PR11 base `main`: `ec0c812ee6b651eb936a24f8e91c346baa9837d8` (PR #45 / M9 PR10 merge)
- PR8 merge: PR #43, `216cea5`
- PR9 merge: PR #44, `49a43fa`
- PR10 merge: PR #45, `ec0c812`
- PR11 branch: `feature/m9-evaluation-v2-stability-release-gate`
- PR11 verified runtime checkpoint: `a12e4549c3cfe738ffffda70885dc1af92e26b09`
- Dataset: `it_operations_v2`, version `2`
- Dataset digest: `26233d82e82633fe890b1f3e52f7cfd26eb4ce59db66a3c35a8ed1de97fa806b`
- Historical V1 digest: `1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4`
- Canary: `it_operations_v2_stability_canary`, version `1`, 10 cases
- Canary digest: `36a6724cac05dffc13e49bc9680e1369344004d9580a83f5f53d775c28e4548b`
- Semantic catalog: `it_operations_semantic_catalog`, version `3`
- Semantic catalog hash: `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`
- Evaluation environment: no frozen live-evidence identity

PR8 made Required Intent deterministic, binding, and fail-closed while keeping Suggested Intent non-binding. PR9 added the minimal deterministic semantic grounding graph. PR10 changed the provider contract to return a `SemanticPlan` only; the backend validates the plan, renders SQL deterministically, applies SQL safety and SQLGlot semantic conformance, and then executes through the restricted runtime role under PostgreSQL RLS. There is no provider SQL, repair call, second provider call, or fallback.

PR11 implements Evaluation V2 semantic contracts, planner and runtime failure-stage measurement, renderer/conformance defect tracking, the fixed V2 canary, three-run stability assessment, exact canary-to-full candidate matching, planner implementation integrity, and fail-closed V2 readiness projection. Historical V1 remains immutable.

## Live measurement

No qualifying OpenAI run has been performed or accepted for this PR11 candidate. No prior diagnostic, V1, filtered, partial, mismatched, or pre-PR11 run is accepted as release evidence. Fresh explicit authorization is required after the source revision and deterministic environment are frozen.

- Provider/model: not available
- Stable canary runs: 0 of 3
- Canary stability assessment: `incomplete`
- Qualifying full V2 run ID: not available
- Full-run gate values: not available
- Safe call/attempt/token/latency totals: not available

The live procedure is three matching executions of the fixed 10-case V2 canary followed, only if stability passes, by one matching complete unfiltered 40-case V2 run. Authorization must identify the exact OpenAI API model and maximum number of billable runs. This report does not authorize a live request.

## Deterministic evidence

PR11's network-free implementation and final branch-wide deterministic checks passed:

- V2 contracts and dataset loader checks: passed
- planner observation, Required Intent adherence, semantic scoring, and failure-stage checks: passed
- deterministic canary selection and digest checks: passed
- three-run stability and fail-closed mismatch/malformed/oscillation checks: passed
- V2 readiness, candidate matching, deterministic-gate, and planner-integrity checks: passed
- backend without PostgreSQL: 1,283 passed, 156 expected PostgreSQL-only skips
- isolated PostgreSQL 16 backend: 1,419 passed, zero skips, plus the exact 20-case M8 release suite passed separately with zero skips
- migrations: fresh upgrade through `0010_disable_inactive_user`, `alembic current`, and `alembic check` passed
- frontend: 280 Vitest tests, ESLint, both TypeScript checks, and production build passed
- Playwright: 12 general Chromium flows and two isolated M8 primary/negative flows passed
- Ruff, Pyright with zero errors/warnings, compileall, and `git diff --check`: passed

The isolated PostgreSQL container and temporary application processes were removed after verification. These results are deterministic implementation evidence only; they do not substitute for live-provider or manual-QA evidence.

## Manual QA

The complete manual QA checklist has not been completed on a frozen PR11 candidate. It is a separate final release-completion requirement on the same unchanged candidate; automated readiness can become `ready` without satisfying manual QA, but Milestone 9 and QueryOps AI V1 still cannot be marked complete until manual QA passes.

## Current release state

| Requirement | State |
| --- | --- |
| PR11 focused deterministic implementation gates | passed |
| Final branch-wide deterministic regression | passed |
| Evaluation V2 framework | implemented |
| Three-run canary evidence | missing |
| Full qualifying V2 run | missing |
| Complete manual QA | missing |
| Automated V1 readiness | `incomplete` |

## Verdict

`incomplete`

PR11 implementation is complete and its local deterministic release gates passed; live release evidence is pending. Automated readiness remains `incomplete` until three matching canary runs are stable and a matching complete V2 full run passes every threshold, deterministic gate, and planner-integrity check with no renderer or conformance defects. Even after automated readiness becomes `ready`, Milestone 9 and QueryOps AI V1 must not be marked complete until the full manual QA checklist passes on that same unchanged candidate.

The authoritative release order is: finish PR11, pass branch CI, merge, pass final `main` CI, freeze that exact `main` SHA, create a fresh V2 environment manifest, obtain exact model/run authorization, run canary ×3, require stability, run the matching full V2 suite, require automated readiness `ready`, complete manual QA on the unchanged candidate, and only then mark the release complete.

This report contains no prompts, SQL, expected or actual rows, provider payloads, secrets, raw errors, database URLs, or evaluator baselines.
