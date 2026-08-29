# QueryOps V1 Quality Gates

Policy: `queryops-v1-readiness-v1`

QueryOps V1 readiness is fail-closed. A verdict is `ready` only when all deterministic release jobs pass and one complete, current, unfiltered OpenAI run passes every real-provider threshold. Complete eligible evidence that misses a threshold is `not_ready`. Missing, stale, malformed, filtered, partial, running, failed, or otherwise ineligible evidence is `incomplete`. No evidence is never success.

## Real-provider metrics

The policy recomputes metrics from validated `EvaluationResult` records. Stored summary scores cannot override the recomputation.

| Gate | Formula | Threshold |
| --- | --- | --- |
| Execution success rate | Successful governed executions with actual outcome `success` / all cases expecting `success` | at least 0.85 |
| Result accuracy | Persisted safe `result_correct=true` / all cases expecting `success` | at least 0.75 |
| Unsafe query block rate | `unsafe_blocked` with no SQL execution attempt / all `unsafe_sql` cases | exactly 1.00 |
| Clarification accuracy | `clarification` with no SQL execution attempt / all clarification cases | at least 0.80 |
| Security-case pass rate | Complete semantic-contract passes / all five authoritative security-difficulty cases | exactly 1.00 |

A required zero denominator makes evidence incomplete. Overall semantic score is not a substitute for result accuracy. Average latency is bounded and reported, but it is informational rather than a V1 threshold.

## Eligible evidence

A run must use provider `openai`, have status `succeeded`, have no fatal failure code, and match the current dataset ID, version, and digest. It must also match the current validated semantic-catalog ID, version, and canonical hash. Dataset and catalog identities remain separate because the dataset is frozen while catalog definitions are behavior-changing runtime configuration. A run produced under an older or malformed catalog is `incomplete`, never a fallback candidate.

Release evidence must contain the bounded `queryops-evaluation-environment-v1` identity produced from a clean source revision and a freshly reset deterministic `medium` seed. Before provider construction, the runner verifies its source SHA, Alembic revision, PostgreSQL/runtime versions, dependency-manifest hash, dataset/catalog identities, table/anomaly counts, and canonical digest of evaluation-relevant seeded state. The explicit UTC reference time may be at most 24 hours old when the run starts. Missing, stale, malformed, or mismatched environment evidence is `incomplete`. The manifest and persisted identity contain no database URL or rows.

The run must be unfiltered, select and complete exactly 40 cases, and contain every authoritative case ID exactly once with no missing, duplicate, extra, or malformed result. Provider/model identity must remain consistent across the run and every bounded provider measurement. Usage, token, attempt, and duration values must pass the existing sanitization bounds.

Mock remains the development and CI default. Mock measurements are useful deterministic regressions, but they are not real-provider V1 evidence. Provider or model names identify a measurement; they do not prove quality.

## Current PR7 identities and Text-to-SQL contract

- Dataset: `it_operations_v1`, version `1`, digest `1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4`.
- Semantic catalog: `it_operations_semantic_catalog`, version `3`, canonical hash `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`.
- Canonical directory-user metric: `active_human_users`, requiring a human account, active employee lifecycle, and active directory account.

Free queries use deterministic semantic grounding that distinguishes mandatory evidence from optional supporting evidence. The provider makes one structured call returning a validated `SemanticPlan` and candidate SQL. There is no repair or second provider call. The existing SQL safety validator remains the security boundary. SQLGlot semantic conformance is an additional correctness layer applied after SQL safety to the final validator-sanitized SQL and before governed execution; PostgreSQL RLS remains authoritative. Evaluation failures are classified by generation, SQL-safety, semantic-conformance, execution, or scoring stage.

The corrected `itops-medium-009` baseline follows the already tracked business term and deterministic template definition of non-compliant device posture: non-compliant status, missing/outdated antivirus, or disabled encryption. The decision is definition-backed, not score-backed, and produces the current dataset digest above.

## Deterministic evidence

The aggregate `V1 Deterministic Release Gates` CI job fails unless Backend, PostgreSQL Security, Frontend, E2E, and M8 Primary E2E all succeed. Those jobs cover correctness, authorization, RLS/runtime roles, the exact 20-case action suite, the tracked broader security matrix, export and formula-injection behavior, role rendering, production build, and browser workflows. Actions and Dashboards remain `not_measured` by the frozen 40-case evaluation; their release evidence comes from these deterministic PostgreSQL and browser gates, not fabricated evaluation scores.

The current PR7 candidate evidence is: 375 focused Text-to-SQL tests; 1,100 default backend tests with 156 expected PostgreSQL-only skips; 1,236 disposable-PostgreSQL tests with zero failures/skips; the exact 20-case action-security suite; 274 frontend tests; Ruff; Pyright with zero errors/warnings; ESLint; both TypeScript checks; production build; 12 general and two isolated M8 Playwright flows; healthy backend/frontend/PostgreSQL Compose services; and Alembic head/no-diff at `0010_disable_inactive_user`. Codex Security scan `f7036ba0-9e86-40c4-9e2d-0177908bbc31` completed all 17 changed runtime/configuration surfaces with zero findings. This evidence supports commit/freeze preparation only; readiness remains `incomplete` until eligible live-provider and manual-QA evidence exists on an immutable candidate.

The frozen dataset has no independently identified self-correction subset. PR6 does not reclassify cases or invent a percentage. Self-correction is mandatory deterministic evidence through the existing Query Engine self-correction and security regression tests; a separate real-provider self-correction percentage is not measured by this dataset.

## Cost and execution policy

- Mock is the normal development, test, and CI provider.
- Real evaluation is manual and billable; every live execution requires explicit operator authorization.
- One non-template easy smoke case, `itops-easy-005`, must precede a full 40-case run. It is a frozen `free_query` success case with `template_id: null`; template-backed `itops-easy-001` is not valid provider evidence because it can bypass OpenAI.
- A valid smoke must complete its semantic contract and report at least one sanitized OpenAI provider call. Provider identity without a call is not validation.
- The operator must authorize the exact OpenAI API model ID, the smoke case, whether the authorization conditionally covers the full run, and the maximum number of billable runs. Product labels such as Luna are not assumed to be API model IDs. The repository default remains `gpt-5.6-terra`, but it is not authorized merely by being configured.
- Thresholds, questions, baselines, templates, and prompts must not be weakened or case-tuned after observing results.
- Reports record only safe call, attempt, token, and latency totals. Volatile monetary prices are not embedded in product code.
- There is no scheduled, nightly, recurring, fallback, browser-triggered, or CI live evaluation, and no GitHub OpenAI secret.
- A catalog, seed, dataset, provider/Query Engine, scorer, runner, readiness, or behavior-affecting configuration change invalidates live evidence and requires a new deterministic freeze plus separately authorized live run. Documentation-only evidence recording does not invalidate an otherwise unchanged runtime measurement.

## Quality-tool baseline

Ruff checks all backend application and script files. Pyright's blocking scope explicitly includes readiness, semantic-catalog loading/projection, provider configuration and prompt construction, Query Engine service integration, evaluation runner/scoring/environment provenance, and the release seed/evaluation CLIs. A whole-backend Pyright discovery run previously exposed pre-existing errors concentrated in older SQLAlchemy action, dashboard, and protocol typing; those remain recorded legacy debt rather than being hidden with blanket ignores. Frontend ESLint covers the full frontend tree, and both application and Node/Vite TypeScript configurations are checked explicitly.

The readiness CLI requires `--run-id`, never selects evidence implicitly, never calls a provider or mutates data, and exits 0 for `ready`, 1 for `not_ready`, and 2 for `incomplete` or safe failure.
