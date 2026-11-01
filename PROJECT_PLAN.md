# QueryOps AI — Project Plan

## Current Status

Active milestone: **M10 — Product Reliability & V1 Completion**. The target is a
reliable, complete **local IT Operations V1 using synthetic data**. Shared or
production deployment, real identity integration, additional domains and new
major capabilities are separate future scope.

**W0 is complete.** [PR #61](https://github.com/Daniel23sh/queryops-ai/pull/61)
integrated bounded-result evidence with focused correctness, metadata and consumer
corrections. Runtime baseline on `main`: `f23099c1a7d9ffaad8bc2c445a6551d77ffa5cb1`;
reviewed feature head: `a3759d8`. Documentation-only reconciliation follows that
runtime baseline. The original `2d7796c` is recoverable locally and remotely at
`codex/archive-m9-bounded-result-2d7796c`. The feature branch has been removed after
integration; no shared history was rewritten.

The modular architecture, plan-only provider, deterministic SQL, PostgreSQL RLS,
explicit scopes and governed actions remain the design. The
[October audit](docs/audits/2026-10-26-project-audit-he.md) is dated diagnostic
evidence, not release qualification. V1 remains **incomplete and unreleased**.

## Active Objective and Approved Scope

**W1 + W2 are merged.** [PR #63](https://github.com/Daniel23sh/queryops-ai/pull/63)
merged at `8cb9c8d55921454337316fb2e1ef9b8be4a6b1a2`. Its reviewed implementation
and passing deterministic CI are recorded in
[development history](docs/history/development-history.md); this is not V1 release
qualification.

**W2a + W3 are merged.** [PR #64](https://github.com/Daniel23sh/queryops-ai/pull/64)
merged at `e20fa7c9193efdb7ab5de6b01a80a3f39b4e30d3`. Its reviewed implementation
and passing deterministic CI are recorded in development history. This remains
implementation evidence, not V1 release qualification.

**W4 + W5 are merged.** [PR #65](https://github.com/Daniel23sh/queryops-ai/pull/65)
merged at `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`. Reviewed implementations,
independent findings/corrections and deterministic evidence are recorded in
[development history](docs/history/development-history.md). V1 remains unreleased.

**W6a — Semantic Reliability Diagnosis** is the active investigation, explicitly
approved by the owner on 2026-11-01. Work on
`investigation/m10-w6a-semantic-diagnosis` from verified main `b1f03a4`.

Investigate F14 candidate recall/catalog coverage, F3 interpretation/business
composition and F11 supported plan algebra/rendering/conformance/comparison.
Freeze exact source, V2 dataset, semantic catalog, provider configuration and
runtime identities. Separate offline deterministic reproduction from historical
provider observations and current unverified model behavior. Use independent
specialists, contrast cases and counter-evidence, then a fresh non-author review.

Deliver a tracked diagnostic report with reproducible probes/coverage matrix,
root-cause attribution/confidence, alternatives, the smallest justified W6b scope,
acceptance/regression/held-out verification and a bounded proposal for any live
experiments needing separate approval. Keep diagnostic and held-out material
separate; no tuning from held-out outcomes.

This is investigation only. Do not change production semantics, prompts, candidate
rules, renderer, conformance, scoring, datasets/baselines, thresholds or gates.
No paid provider calls, qualifying Canary or Full40 sequence is authorized. Commit
and push the report/planning work in an unmerged PR; W6b is not approved.

The three diagnostic investigations and coordinator replays are complete; final
independent review is pending. The [W6a diagnostic report](docs/audits/2026-11-01-w6a-semantic-diagnosis-he.md)
separates candidate availability, historical/current-unverified provider behavior,
supported plan encodings and evaluator proof. It proposes deterministic output
identity as the first bounded W6b correction because canonical joined outputs can
lose a value through duplicate column labels. This is a proposal, not approval.

## Constraints and Remaining Work

- Follow the [M10 roadmap](docs/development/m10-completion-roadmap.md) for W6a–W9
  dependencies/acceptance; W10 cleanup is optional. W6a diagnosis, W6b targeted
  correction and W6c independent validation are separate packages.
- Old environment v1/missing-fingerprint evidence cannot qualify under environment
  v2. Semantic diagnosis is active; correction and independent validation,
  explicit local auth boundary, reproducible validation and final V1 QA remain open.
  The audit's hard-004 case passed its diagnostic canary; blanket historical
  failure claims are not accepted without new evidence.
- Preserve authorization, RLS, safety caps, historical V1 baselines, semantic
  correctness and thresholds. No result-driven dataset tuning or new major scope.
- Mock remains the default. No qualifying live evidence exists for this baseline;
  W5 identity and all release prerequisites must be complete before a separately
  authorized exact-model/run canary/full sequence. Full manual QA remains open.
- Never use user databases for destructive validation. Preserve unrelated changes
  and protect unique work before any destructive Git operation.

## Next Approved Work

Complete W6a diagnosis and propose the next bounded decision only. Keep the PR
**unmerged**; do not implement W6b or later packages. Any live experiment requires
separate exact-model/case/call-budget approval after feasible offline work.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [W0 decision and verification history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
