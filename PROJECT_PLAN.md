# QueryOps AI — Project Plan

## 1. Current Status

PR52 is merged on main at `4263fc5b29dea9d2ff8367cfefd1eb219cab239d`. PR53 offline semantic-ownership migration evidence is the current approved work. Production Required Intent, provider behavior, and Evaluation V2 remain unchanged. No provider runs are authorized. A later release candidate must be explicitly re-frozen before qualifying evidence is collected.

Milestones 0–8 are complete. Milestone 9 implementation through PR11 is complete and merged. Evaluation V2, the fixed three-run stability canary, matching full-run readiness rules, bounded readiness projection, and deterministic release gates are implemented.

QueryOps AI V1 is **incomplete**, not production-ready, and not released. No qualifying live OpenAI evidence or complete manual QA has been accepted for the merged PR11 candidate.

## 2. Active Objective

Implement and review PR53: an offline authority inventory, independent architecture fixtures, and legacy-versus-proposed structural-binding comparison using the same supplied SemanticPlan. Produce migration gaps for PR54/PR56 without production integration or changing runtime ownership.

V1 release validation remains pending on an explicitly frozen, immutable runtime candidate. The diagnostic baseline above does not establish new qualifying release evidence.

The required order is: freeze the exact candidate SHA; create a fresh manifest-verified Evaluation V2 environment; obtain explicit billable-run authorization; run the fixed 10-case canary three times; require stability; run one matching unfiltered 40-case V2 evaluation; require automated readiness `ready`; complete manual QA on the same unchanged candidate; then record the release verdict.

## 3. Approved Scope

- PR53 offline inventory, independent fixtures, shadow comparison, tests, and migration report. Reuse PR52 structural diagnostics; preserve runtime/provider code, SemanticPlan, V2 assets/digest, scoring, and readiness.
- Complete V3 validation and independent review, then commit, push, and open PR53 without merging. No provider, SQL-execution, database, or persistence work is authorized.
- The release-validation steps below remain subject to their existing authorization and evidence gates; they are not part of PR53.
- Verify and explicitly freeze the runtime candidate source SHA and deterministic evidence.
- Create a fresh deterministic medium-seed Evaluation V2 environment manifest for that SHA.
- After explicit authorization, execute exactly the authorized OpenAI canary runs.
- Run the matching full 40-case V2 evaluation only after the three-run stability gate passes.
- Assess readiness using the existing `queryops-v1-readiness-v1` policy and tracked evidence rules.
- Complete and record every item in `docs/qa/v1-manual-qa.md` on the same unchanged candidate.
- Make documentation-only evidence updates that do not alter the measured runtime.
- Apply only a narrowly proven general-product defect fix if release validation exposes one; include regression coverage, invalidate prior live evidence, and restart the freeze/evidence sequence.

## 4. Explicit Out of Scope

- New product features, milestones, actions, providers, domain packs, or post-M9 work outside the explicitly approved PR53 offline migration evidence.
- Runtime structural-ownership changes, semantic normalization, parser/grounding fixes, dataset changes, and production integration. PR54+ remain future work.
- Evaluation dataset, baseline, template, semantic-contract, prompt, threshold, canary-membership, grounding, graph-ranking, renderer, or runtime tuning in response to observed scores.
- Provider-generated SQL, repair calls, second provider calls, fallbacks, browser-triggered evaluation, provider/key settings, run history/comparison, or arbitrary run selection.
- Authorization, permission, scope, PostgreSQL RLS, runtime-role, schema, migration, normal seed, Action Engine, audit, notification, dashboard, or export changes unless a release-blocking defect is independently demonstrated and explicitly kept within the narrow fix allowance above.
- Scheduled/nightly live evaluation, live-provider CI, background workers, queues, Redis, external notification delivery, billing integration, or deployment work.
- Treating deterministic Mock results, partial/filtered runs, prior V1 evidence, or manual spot checks as qualifying V2 release evidence.

## 5. Constraints / Invariants

- Historical `it_operations_v1` remains immutable. Release evidence uses `it_operations_v2` version 2 and its tracked digest.
- PR8 binding Required Intent/non-binding Suggested Intent, PR9 minimal semantic graph selection, and PR10 plan-only provider plus deterministic backend SQL rendering remain unchanged.
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
- Stop after the PR53 checkpoint. PR54 relational validation, PR55 candidate projection, PR56 ownership migration, and optional PR57 measures are future work, not implementation authority in this task.

## 7. Next Approved Work

Complete PR53 offline migration evidence and independent review; open the PR and do not merge automatically. No runtime ownership change or provider run is approved. See [the PR53 migration report](docs/development/semantic-ownership-migration.md) for experiment boundaries and findings.

## 8. References

- [`AGENTS.md`](AGENTS.md) — permanent repository-specific agent rules and invariants.
- [`README.md`](README.md) — supported product behavior, setup, and verification commands.
- [`docs/evaluation/v1-quality-gates.md`](docs/evaluation/v1-quality-gates.md) — authoritative readiness policy, identities, thresholds, and evidence sequence.
- [`docs/evaluation/v1-readiness-report.md`](docs/evaluation/v1-readiness-report.md) — current release evidence and verdict.
- [`docs/qa/v1-manual-qa.md`](docs/qa/v1-manual-qa.md) — required manual release checklist.
- [`docs/history/development-history.md`](docs/history/development-history.md) — completed milestones, merged PRs, selected historical evidence, and superseded decisions.
- Local ignored `docs/planning/` documents — authoritative detailed product, architecture, security, API, UX, and evaluation specifications when present; never stage or commit them.
