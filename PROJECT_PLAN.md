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

**W6a is merged.** [PR #66](https://github.com/Daniel23sh/queryops-ai/pull/66)
merged at `dac8031bd368f0d17fb94818369cd3071bf8160e`; remote metadata, ancestry
and the diagnostic findings were verified before this task. Its dated findings
remain in the [Hebrew report](docs/audits/2026-11-01-w6a-semantic-diagnosis-he.md).

**W6b Output Identity is merged.** [PR #67](https://github.com/Daniel23sh/queryops-ai/pull/67)
merged at `722e6a092b53dd58b7f9779393273ed13cc70c33`. Its CI selection finding
was corrected at `f43d630`, then independently re-reviewed READY TO MERGE before
integration. Historical evidence is in development history.

**W6b — Candidate Availability** is explicitly approved by the owner as a separate
follow-up on 2026-11-01, on `feature/m10-w6b-candidate-availability` from verified
main `722e6a0`. Compare narrow catalog vocabulary, bounded authorized entity/
relationship availability and selective definition inclusion; implement only an
evidence-supported correction with the existing 16,000-byte cap and security
boundaries. Measure W6a corpus before/after by component, including regressions,
negative controls, deterministic budget/dependency closure and real PostgreSQL/API
permission boundaries. Availability is not provider selection or answer quality.

Preserve one structured-plan provider call, deterministic SQL, non-binding
lexical/connector guidance, exact permissions/scopes and RLS. No frozen dataset,
prompt/model, thresholds, release-gate changes, paid runs, W6c or W7 are approved.
Commit/push a focused PR and leave it unmerged for independent final review. The
known W6a corpus is regression material; the reviewer owns new unseen cases.

Implementation is complete locally: authorized optional graph availability and
atomic definition bundles retain the ranked core and 16,000-byte cap. Known W6a
positive coverage is 40/69 → 69/69; five literal empty-context controls change
without authorizing forbidden targets. See the [decision/evidence](docs/audits/2026-11-01-candidate-availability-he.md).
The implementation is not merged or independently accepted. No claim of provider
answer quality or release qualification follows from these availability metrics.

## Constraints and Remaining Work

- Follow the [M10 roadmap](docs/development/m10-completion-roadmap.md) for W6a–W9
  dependencies/acceptance; W10 cleanup is optional. W6a diagnosis, W6b targeted
  correction and W6c independent validation are separate packages.
- Old environment v1/missing-fingerprint evidence cannot qualify under environment
  v2. Semantic diagnosis and Output Identity are merged; Candidate Availability, independent validation,
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

Complete the Candidate Availability verification/PR handoff, then obtain the
separate independent final review on the unmerged combined diff. Do not begin W6c,
W7 or prompt/model tuning; no paid evaluation is authorized.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [W0 decision and verification history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
