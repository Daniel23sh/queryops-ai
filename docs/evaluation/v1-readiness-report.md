# QueryOps V1 Readiness Report

Policy: `queryops-v1-readiness-v1`

## Source state

- Verified PR11 base `main`: `ec0c812ee6b651eb936a24f8e91c346baa9837d8` (PR #45 / M9 PR10 merge)
- PR8 merge: PR #43, `216cea5`
- PR9 merge: PR #44, `49a43fa`
- PR10 merge: PR #45, `ec0c812`
- PR11 branch: `feature/m9-evaluation-v2-stability-release-gate`
- PR11 implementation commit: not yet frozen
- Dataset: `it_operations_v2`, version `2`
- Dataset digest: `913f8232a795ff59dd2a4ffc5b657bf69239c16182f257fd2850b68d9003de9b`
- Historical V1 digest: `1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4`
- Canary: `it_operations_v2_stability_canary`, version `1`, 10 cases
- Canary digest: `a32105296cf0017aa48124470acd95952df72a156b50aa37710762e5f11494cd`
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

PR11's staged network-free implementation checks through the Evaluation workspace passed:

- V2 contracts and dataset loader checks: passed
- planner observation, Required Intent adherence, semantic scoring, and failure-stage checks: passed
- deterministic canary selection and digest checks: passed
- three-run stability and fail-closed mismatch/malformed/oscillation checks: passed
- V2 readiness, candidate matching, deterministic-gate, and planner-integrity checks: passed
- frontend Evaluation readiness projection: 274 Vitest tests, ESLint, both TypeScript checks, and production build passed

The final branch-wide backend, disposable-PostgreSQL, migration, security/RLS, and browser regression checkpoint is still to be recorded on the frozen PR11 candidate. The earlier PR7 full deterministic evidence remains historical baseline evidence and is not presented as proof of this changed runtime.

## Manual QA

The complete manual QA checklist has not been completed on a frozen PR11 candidate. Automated tests and live evaluation metrics cannot substitute for this requirement.

## Current release state

| Requirement | State |
| --- | --- |
| PR11 focused deterministic implementation gates | passed |
| Final branch-wide deterministic regression | pending |
| Evaluation V2 framework | implemented |
| Three-run canary evidence | missing |
| Full qualifying V2 run | missing |
| Complete manual QA | missing |
| V1 readiness | `incomplete` |

## Verdict

`incomplete`

PR11 implementation is not yet frozen and live release evidence is pending. Milestone 9 and QueryOps AI V1 must not be marked complete until all deterministic gates pass on the immutable candidate, three matching canary runs are stable, a matching complete V2 full run passes every threshold with no renderer or conformance defects, and the full manual QA checklist passes on that unchanged candidate.

This report contains no prompts, SQL, expected or actual rows, provider payloads, secrets, raw errors, database URLs, or evaluator baselines.
