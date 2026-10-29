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

**W2a + W3 — Scoped Evaluation & Reliable Result Delivery** is the active batch,
explicitly authorized by the owner on 2026-10-29. Work on
`feature/m10-evaluation-reads-result-delivery`, from verified main `8cb9c8d`.
Keep the resulting PR unmerged for final approval.

W2a: replace the scoped latest-run `DISTINCT` over JSON without expanding access.
Preserve ordering, candidate limits, dataset identity, visible-result projections
and hidden-run/count/evidence nondisclosure. Verify empty/visible/inaccessible
Manager/Analyst states and Admin/global controls on actual PostgreSQL and browser
APIs, without route mocks or a speculative migration.

W3: preserve trusted delivery completeness and bound origin through Query Run,
Saved Query, Card refresh, visualization and CSV. Distinguish requested top-N from
safety bounds, and database delivery from visual clipping. Disclose partial or
unknown delivery without inventing population totals or adding non-data rows to
CSV. Preserve current-viewer authorization, RLS, SQL validation, safety caps,
restricted export policy, CSV sanitization and audit; persist no result rows or
evaluator auxiliary evidence. Exercise above-cap and intact top-N cases on
disposable PostgreSQL, frontend and real browser flows.

Separate implementation ownership and identifiable commits are required, followed
by combined V3 verification and a fresh-context independent non-author review.

## Constraints and Remaining Work

- Follow the [M10 roadmap](docs/development/m10-completion-roadmap.md) for W2a–W9
  dependencies/acceptance; W10 cleanup is optional. W6a diagnosis, W6b targeted
  correction and W6c independent validation are separate packages.
- Scoped Evaluation JSON DISTINCT reads and derived card/CSV delivery disclosure
  are this batch's defects, not completed work yet. Dashboard editing/value
  mapping, semantic reliability and complete provider/config identity remain open.
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

Complete and hand off W2a + W3 only; keep the PR **unmerged**. Do not start W4,
W5 or later packages. No paid provider, Canary or Full40 run is authorized.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [W0 decision and verification history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
