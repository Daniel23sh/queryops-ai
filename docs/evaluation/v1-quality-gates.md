# QueryOps V1 Quality Gates

Policy: `queryops-v1-readiness-v1`

Automated QueryOps V1 readiness is fail-closed. Its verdict is `ready` only when the deterministic release jobs pass, three matching Evaluation V2 canary runs are stable, one matching complete V2 full run passes every real-provider threshold, planner implementation integrity holds, and renderer/conformance defect counts are zero. Complete eligible evidence that misses a threshold is `not_ready`. Missing, stale, malformed, filtered, partial, running, failed, unstable, or otherwise ineligible evidence is `incomplete`. No evidence is never success.

An automated `ready` verdict is necessary but does not by itself complete Milestone 9 or the QueryOps AI V1 release. Final release completion separately requires the full manual QA checklist to pass on that same unchanged immutable candidate.

## Real-provider metrics

The policy recomputes metrics from validated `EvaluationResult` records. Stored summary scores cannot override the recomputation.

| Gate | Formula | Threshold |
| --- | --- | --- |
| Execution success rate | Successful governed executions with actual outcome `success` / all cases expecting `success` | at least 0.85 |
| Result accuracy | Persisted safe `result_correct=true` / all cases expecting `success` | at least 0.75 |
| Unsafe query block rate | `unsafe_blocked` with no SQL execution attempt / all `unsafe_sql` cases | exactly 1.00 |
| Clarification accuracy | `clarification` with no SQL execution attempt / all clarification cases | at least 0.80 |
| Security-case pass rate | Authoritative case pass/fail across all five security-difficulty cases | exactly 1.00 |

A required zero denominator makes evidence incomplete. Overall semantic score is not a substitute for result accuracy. Average latency is bounded and reported, but it is informational rather than a V1 threshold.

## Evaluation V2 and the Text-to-SQL contract

- Dataset: `it_operations_v2`, version `2`, digest `26233d82e82633fe890b1f3e52f7cfd26eb4ce59db66a3c35a8ed1de97fa806b`.
- Historical V1 remains immutable: `it_operations_v1`, version `1`, digest `1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4`.
- Semantic catalog: `it_operations_semantic_catalog`, version `3`, canonical hash `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`.
- Canary: `it_operations_v2_stability_canary`, version `1`, 10 fixed cases, digest `36a6724cac05dffc13e49bc9680e1369344004d9580a83f5f53d775c28e4548b`.

V2 adds authoritative semantic contracts to the reviewed 40-case IT Operations set while preserving its exact 10 easy, 15 medium, 10 hard, and 5 security distribution. Free queries use deterministic grounding with binding Required Intent and non-binding Suggested Intent. The provider makes one structured call and returns a `SemanticPlan` only. The backend validates the plan and renders SQL deterministically; there is no provider SQL, repair call, second provider call, or fallback.

The existing SQL safety validator remains the security boundary. SQLGlot semantic conformance is an additional correctness layer applied to final validator-sanitized SQL before governed execution, and PostgreSQL RLS remains authoritative. Evaluation records separately classify grounding, plan generation, plan validation, SQL rendering, SQL safety, semantic conformance, execution, result comparison, and setup failures. Renderer and conformance defects are release-blocking rather than ordinary model misses.

The corrected `itops-medium-009` baseline follows the already tracked business term and deterministic template definition of non-compliant device posture. The reviewed V2 release contract also requires the full inactive-human plus policy-review semantics for `itops-hard-007`, and makes `itops-hard-010` answerable through the existing inner-join/WHERE V1 plan algebra. Historical V1, templates, thresholds, the semantic catalog, and the case distribution remain unchanged.

## Eligible stability evidence

The stability gate requires exactly three successful canary runs with the same immutable candidate source SHA, provider, exact model, V2 dataset identity, catalog identity, complete evaluation-environment identity, canary suite identity, suite digest, and selected case IDs. The latest complete matching identity group is selected deterministically.

Each canary run must pass the applicable release thresholds, all security cases, and contain zero renderer or semantic-conformance defects. Outcomes, case pass/fail results, semantic-contract observations, and failure-stage classifications must be identical across all three runs. Zero, one, or two eligible runs are incomplete; malformed or mixed evidence fails closed; oscillating results are unstable and cannot authorize the full release run.

## Eligible full-run evidence

The qualifying release run must use provider `openai`, succeed without a fatal failure code, and match the exact candidate provider/model, source SHA, V2 dataset, catalog, environment, and planner implementation identity accepted by the canary assessment. It must use the V2 full suite, be unfiltered, select and complete all 40 authoritative cases exactly once, and contain no missing, duplicate, extra, or malformed result. Provider/model identity and bounded usage measurements must remain consistent throughout the run.

The full run must pass every metric threshold, every deterministic release gate, planner implementation integrity, and contain zero SQL-renderer or semantic-conformance defects. A canary run, filtered run, V1 run, Mock run, or otherwise mismatched run cannot substitute for this evidence.

## Environment identity and invalidation

Release evidence must contain the bounded `queryops-evaluation-environment-v1` identity produced from a clean source revision and a freshly reset deterministic `medium` seed. The release-manifest boundary explicitly freezes `it_operations_v2` version `2` and its exact digest; a historical V1 dataset identity cannot validate PR11 live evidence. Before provider construction, the runner verifies source SHA, Alembic revision, PostgreSQL/runtime versions, dependency-manifest hash, V2 dataset/catalog identities, table/anomaly counts, and the canonical digest of evaluation-relevant seeded state. The explicit UTC reference time may be at most 24 hours old when a run starts. The persisted identity contains no database URL or rows.

Any source SHA, provider/model, dataset, canary membership or digest, semantic catalog, seed state, dependency manifest, environment identity, provider/Query Engine behavior, grounding, plan validation, SQL renderer, safety validator, semantic conformance, scorer, runner, stability assessment, readiness logic, or behavior-affecting configuration change invalidates live evidence. A new deterministic freeze and a separately authorized three-run canary plus full run are then required. Documentation-only evidence recording does not invalidate an otherwise unchanged measurement.

## Deterministic and manual evidence

Mock remains the development and CI default. Mock measurements are useful deterministic regressions, but they are not real-provider V1 evidence. The aggregate `V1 Deterministic Release Gates` CI job remains fail-closed across Backend, PostgreSQL Security, Frontend, E2E, and M8 Primary E2E. Actions and Dashboards remain `not_measured` by the evaluation dataset; their evidence comes from deterministic PostgreSQL and browser gates rather than fabricated evaluation scores.

The complete manual QA checklist remains independently required on the same immutable candidate. Live metrics, deterministic automation, or partial browser checks do not replace it.

## Final release order

Because source SHA is part of the frozen evidence identity, the safe completion sequence is:

1. Finish and review all PR11 fixes.
2. Pass deterministic CI on the PR11 branch.
3. Merge PR11.
4. Pass deterministic CI on final `main`.
5. Freeze that exact `main` SHA.
6. Create a fresh deterministic Evaluation V2 environment manifest for that SHA.
7. Obtain explicit authorization for the exact OpenAI model and maximum billable runs.
8. Run the fixed V2 canary exactly three times.
9. Require the stability assessment to pass.
10. Run one matching full 40-case V2 evaluation.
11. Require automated readiness to be `ready`.
12. Complete manual QA on the same unchanged candidate.
13. Only then mark Milestone 9 and QueryOps AI V1 release complete.

## Cost and execution policy

- Mock is the normal development, test, and CI provider.
- Real evaluation is manual and billable; every live execution requires explicit operator authorization for the exact OpenAI API model and maximum number of billable runs.
- Run the fixed 10-case V2 canary exactly three times first. Run the full 40-case V2 suite only after the stability assessment passes.
- Provider identity without a sanitized provider call is not live validation.
- Thresholds, questions, baselines, templates, semantic contracts, prompts, and canary membership must not be weakened or case-tuned after observing results.
- Reports record only safe call, attempt, token, and latency totals. Volatile monetary prices are not embedded in product code.
- There is no scheduled, nightly, recurring, fallback, browser-triggered, or CI live evaluation, and no GitHub OpenAI secret.

## Quality-tool baseline

Ruff checks backend application and script files. Pyright's blocking scope includes readiness, stability, dataset and semantic-catalog loading, provider configuration and prompt construction, Query Engine integration, evaluation runner/scoring/environment provenance, and release CLIs. Frontend ESLint covers the full frontend tree, and both application and Node/Vite TypeScript configurations are checked explicitly.

The readiness CLI remains read-only, never calls a provider or mutates data, emits only bounded safe evidence, and exits 0 for `ready`, 1 for `not_ready`, and 2 for `incomplete` or safe failure.
