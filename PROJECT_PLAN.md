# QueryOps AI — Project Plan

## 1. Current Status

PR #46 (`M9 PR11 — Evaluation V2 & Stability Release Gate`) merged at `757187ace074d83b075ba2550f8dd6a2c50d64a1`, and its branch and final merged-`main` GitHub checks passed: Backend, PostgreSQL Security, Frontend, E2E, M8 Primary E2E, and V1 Deterministic Release Gates. That revision is the current runtime/release candidate unless explicitly superseded. Repository Git HEAD may advance through documentation-only commits without silently replacing the runtime candidate.

Milestones 0–8 are complete. Milestone 9 implementation through PR11 is complete and merged. Evaluation V2, the fixed three-run stability canary, matching full-run readiness rules, bounded readiness projection, and deterministic release gates are implemented.

QueryOps AI V1 is **incomplete**, not production-ready, and not released. No qualifying live OpenAI evidence or complete manual QA has been accepted for the merged PR11 candidate.

## 2. Active Objective

PR52 is implemented locally on diagnostic baseline `9eb094ab14d8ae5ef05e5a0d5a52cb8ce13287af` and is in final review. It adds the semantic-intent foundation and offline V2 structural-conformance harness only. Do not wire the foundation or audit into production execution, evaluation scoring, or readiness, and do not tune grounding or frozen V2 assets from the findings.

V1 release validation remains pending on an explicitly frozen, immutable runtime candidate. The diagnostic baseline above does not establish new qualifying release evidence.

The required order is: freeze the exact candidate SHA; create a fresh manifest-verified Evaluation V2 environment; obtain explicit billable-run authorization; run the fixed 10-case canary three times; require stability; run one matching unfiltered 40-case V2 evaluation; require automated readiness `ready`; complete manual QA on the same unchanged candidate; then record the release verdict.

## 3. Approved Scope

- PR52 Chunk 2 foundation only, as described in [the foundation design](docs/development/semantic-intent-foundation.md). Preserve runtime behavior, provider prompts/schemas, Evaluation V2 artifacts and digests, and readiness thresholds. No provider/API calls are authorized for this chunk.
- PR52 Chunk 3 offline V2 structural-conformance harness: deterministically compare required and suggested grounding with frozen V2 structural contracts, print safe reports to stdout or `/tmp`, and stop after the first audit. No provider, database, SQL-execution, persistence, scoring, readiness, or runtime integration is authorized.
- PR52 Chunk 4 finalization: document frozen audit findings, complete validation and independent review, and prepare the branch for review without beginning parser or grounding changes.
- The release-validation steps below remain subject to their existing authorization and evidence gates; they are not part of Chunk 2.
- Verify and explicitly freeze the runtime candidate source SHA and deterministic evidence.
- Create a fresh deterministic medium-seed Evaluation V2 environment manifest for that SHA.
- After explicit authorization, execute exactly the authorized OpenAI canary runs.
- Run the matching full 40-case V2 evaluation only after the three-run stability gate passes.
- Assess readiness using the existing `queryops-v1-readiness-v1` policy and tracked evidence rules.
- Complete and record every item in `docs/qa/v1-manual-qa.md` on the same unchanged candidate.
- Make documentation-only evidence updates that do not alter the measured runtime.
- Apply only a narrowly proven general-product defect fix if release validation exposes one; include regression coverage, invalidate prior live evidence, and restart the freeze/evidence sequence.

## 4. Explicit Out of Scope

- New product features, milestones, actions, providers, domain packs, or post-M9 work outside the explicitly approved PR52 foundation.
- PR52 runtime integration, semantic normalization, parser/grounding fixes, dataset changes, and replacement of grounding heuristics before a later checkpoint approval.
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

- Exact OpenAI API model and maximum billable run count have not been authorized for this candidate.
- Stable canary evidence is 0 of 3.
- No matching complete 40-case V2 OpenAI run exists.
- Manual QA is not performed.
- PR52 must stop after finalization before any parser, grounding, dataset, scoring, or runtime change. Billable live validation remains separately unauthorized.

## 7. Next Approved Work

Complete review and merge handling for PR52 only. PR53, parser fixes, grounding changes, dataset changes, semantic normalization, and production integration are not approved. PR #46 revision `757187ace074d83b075ba2550f8dd6a2c50d64a1` remains the documented runtime candidate unless explicitly superseded; provider calls require separate exact model/run authorization.

## 8. References

- [`AGENTS.md`](AGENTS.md) — permanent repository-specific agent rules and invariants.
- [`README.md`](README.md) — supported product behavior, setup, and verification commands.
- [`docs/evaluation/v1-quality-gates.md`](docs/evaluation/v1-quality-gates.md) — authoritative readiness policy, identities, thresholds, and evidence sequence.
- [`docs/evaluation/v1-readiness-report.md`](docs/evaluation/v1-readiness-report.md) — current release evidence and verdict.
- [`docs/qa/v1-manual-qa.md`](docs/qa/v1-manual-qa.md) — required manual release checklist.
- [`docs/history/development-history.md`](docs/history/development-history.md) — completed milestones, merged PRs, selected historical evidence, and superseded decisions.
- Local ignored `docs/planning/` documents — authoritative detailed product, architecture, security, API, UX, and evaluation specifications when present; never stage or commit them.
