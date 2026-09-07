# QueryOps AI — Project Plan

## 1. Current Status

PR52–PR56 are merged, including relational validation and candidate/path completeness. PR57 semantic-ownership cutover is the current implementation checkpoint, based on verified main `be218b43b8c7120a043d3113c7562ef5e9293168`. Free-question interpretation moves to the planner; Evaluation V2 remains unchanged. No provider runs are authorized. A later release candidate must be explicitly re-frozen before qualifying evidence is collected.

Milestones 0–8 are complete. Milestone 9 implementation through PR11 is complete and merged. Evaluation V2, the fixed three-run stability canary, matching full-run readiness rules, bounded readiness projection, and deterministic release gates are implemented.

QueryOps AI V1 is **incomplete**, not production-ready, and not released. No qualifying live OpenAI evidence or complete manual QA has been accepted for the merged PR11 candidate.

## 2. Active Objective

Implement and review PR57: make question-derived lexical and structural heuristics candidate retrieval/guidance only. The provider interprets natural language as the existing SemanticPlan; selected catalog definitions, authorization, relational proofs, compilation and conformance remain deterministic. Preserve PR55/PR56 and explicitly version diagnostic reruns without rewriting historical evidence.

V1 release validation remains pending on an explicitly frozen, immutable runtime candidate.

The required order is: freeze the exact candidate SHA; create a fresh manifest-verified Evaluation V2 environment; obtain explicit billable-run authorization; run the fixed 10-case canary three times; require stability; run one matching unfiltered 40-case V2 evaluation; require automated readiness `ready`; complete manual QA on the same unchanged candidate; then record the release verdict.

## 3. Approved Scope

- PR57 atomic grounding/prompt/validation cutover, independent paraphrase and contrast regressions, and diagnostic compatibility. Required Intent remains fail-closed but is not populated from free-question wording.
- Complete V3 validation and independent review; commit, push, and open PR57 without merging. PostgreSQL is not required unless database-dependent behavior changes. No provider runs are authorized.
- The release-validation steps below remain subject to their existing authorization and evidence gates; they are not part of PR57.
- Verify and explicitly freeze the runtime candidate source SHA and deterministic evidence.
- Create a fresh deterministic medium-seed Evaluation V2 environment manifest for that SHA.
- After explicit authorization, execute exactly the authorized OpenAI canary runs.
- Run the matching full 40-case V2 evaluation only after the three-run stability gate passes.
- Assess readiness using the existing `queryops-v1-readiness-v1` policy and tracked evidence rules.
- Complete and record every item in `docs/qa/v1-manual-qa.md` on the same unchanged candidate.
- Make documentation-only evidence updates that do not alter the measured runtime.
- Apply only a narrowly proven general-product defect fix if release validation exposes one; include regression coverage, invalidate prior live evidence, and restart the freeze/evidence sequence.

## 4. Explicit Out of Scope

- New product features, milestones, actions, providers, domain packs, or post-M9 work outside the explicitly approved PR57 cutover.
- Dataset changes and PR58 measures/grains, which remains optional future work.
- Evaluation dataset, baseline, template, semantic-contract, prompt, threshold, canary-membership, grounding, graph-ranking, renderer, or runtime tuning in response to observed scores.
- Provider-generated SQL, repair calls, second provider calls, fallbacks, browser-triggered evaluation, provider/key settings, run history/comparison, or arbitrary run selection.
- Authorization, permission, scope, PostgreSQL RLS, runtime-role, schema, migration, normal seed, Action Engine, audit, notification, dashboard, or export changes unless a release-blocking defect is independently demonstrated and explicitly kept within the narrow fix allowance above.
- Scheduled/nightly live evaluation, live-provider CI, background workers, queues, Redis, external notification delivery, billing integration, or deployment work.
- Treating deterministic Mock results, partial/filtered runs, prior V1 evidence, or manual spot checks as qualifying V2 release evidence.

## 5. Constraints / Invariants

- Historical `it_operations_v1` remains immutable. Release evidence uses `it_operations_v2` version 2 and its tracked digest.
- Required Intent retains binding semantics for a future independently trusted structured source; no such source is introduced. Free questions populate only non-binding guidance. PR10 plan-only provider/renderer ownership and PR56 candidate completeness remain intact; the provider selects the executable relationship tree.
- SQL safety, semantic conformance, effective-permission/resource authorization, `queryops_query_runtime`, transaction-local access context, and PostgreSQL RLS remain authoritative.
- Mock remains the development and CI default. A real OpenAI call requires explicit authorization for the exact API model and maximum billable run count.
- Repository HEAD and the runtime candidate are distinct identities. Documentation-only commits may advance `main`; qualifying evidence remains bound to the explicitly frozen runtime source SHA.
- Canary evidence requires exactly three complete, stable runs with identical candidate, provider/model, dataset, catalog, environment, suite, and planner identities.
- The full run must be unfiltered, contain all 40 V2 cases exactly once, and match the accepted canary candidate identity.
- Renderer and semantic-conformance defects are release blockers, not ordinary model misses.
- Manual QA is independently required on the same unchanged candidate even if automated readiness becomes `ready`.
- Any behavior-affecting change invalidates live evidence and requires a new freeze and separately authorized evidence sequence.

## 6. Blockers / Open Decisions

- No provider runs are authorized; an exact OpenAI API model and maximum billable run count would require separate approval for a later explicitly frozen candidate.
- Stable canary evidence is 0 of 3.
- No matching complete 40-case V2 OpenAI run exists.
- Manual QA is not performed.
- Stop after opening PR57. PR58 measures/grains remains optional and is not authorized here.

## 7. Next Approved Work

Complete PR57 semantic-ownership cutover and independent review; open the PR and do not merge automatically. No provider run is approved. PR58 measures/grains remains optional. See [PR55 relational guarantees](docs/development/relational-semantic-validation.md) and [ownership and historical PR53 evidence](docs/development/semantic-ownership-migration.md).

## 8. References

- [`AGENTS.md`](AGENTS.md) — permanent repository-specific agent rules and invariants.
- [`README.md`](README.md) — supported product behavior, setup, and verification commands.
- [`docs/evaluation/v1-quality-gates.md`](docs/evaluation/v1-quality-gates.md) — authoritative readiness policy, identities, thresholds, and evidence sequence.
- [`docs/evaluation/v1-readiness-report.md`](docs/evaluation/v1-readiness-report.md) — current release evidence and verdict.
- [`docs/qa/v1-manual-qa.md`](docs/qa/v1-manual-qa.md) — required manual release checklist.
- [`docs/history/development-history.md`](docs/history/development-history.md) — completed milestones, merged PRs, selected historical evidence, and superseded decisions.
- Local ignored `docs/planning/` documents — authoritative detailed product, architecture, security, API, UX, and evaluation specifications when present; never stage or commit them.
