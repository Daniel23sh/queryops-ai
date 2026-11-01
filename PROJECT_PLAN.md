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

**W4 + W5 — Product Correctness & Evaluation Integrity** is the active batch,
explicitly authorized by the owner on 2026-10-31. Implement on
`feature/m10-dashboard-evaluation-integrity` from verified main `e20fa7c`.
W5 `515e057`, W4 `f13c4ad`, UI/CI integration `5acfb1e` and reviewed timeout
correction `178f132` are implemented. Final local V3 verification passed 1,921
PostgreSQL backend tests plus 20 action-security cases without skips, 318 frontend
tests and 36 Chromium flows. Independent review/re-review has no unresolved
findings. [PR #65](https://github.com/Daniel23sh/queryops-ai/pull/65) is open and
**unmerged** for owner approval; final-head CI must pass before merge.
This does not qualify V1. Decisions/evidence are in development history.

W4: preserve unsaved Dashboard layout edits through non-conflicting metadata/Card
operations, reconcile or explicitly resolve conflicts, and keep layout versions,
save/cancel/failure and navigation behavior consistent. Correct numeric KPI and
chart mappings without treating total/target-like names as an automatic exclusion
from primary measures. Preserve legitimate gauges and manual overrides. Use
compositional component tests and actual PostgreSQL-backed browser workflows.

W5: version and persist one deterministic, secret-free provider/runtime identity
covering behavior-affecting settings and installed dependency versions. Manifest
creation/validation, persistence, stability and readiness must share this contract;
old/malformed/missing identity is incomplete, never upgraded through defaults.
Separate logical calls, measured HTTP attempts or explicitly unknown attempts,
and observed versus unavailable usage on retry/failure paths. Keep provider safety,
historical baselines, thresholds and fail-closed qualification unchanged.

Use separate implementation ownership and identifiable commits, combined V3
verification and a fresh independent reviewer who authored neither package.

## Constraints and Remaining Work

- Follow the [M10 roadmap](docs/development/m10-completion-roadmap.md) for W4–W9
  dependencies/acceptance; W10 cleanup is optional. W6a diagnosis, W6b targeted
  correction and W6c independent validation are separate packages.
- Dashboard editing/value mapping and provider/runtime identity have reviewed
  implementation and executable evidence on the branch; main integration is
  pending. Old environment v1/missing-fingerprint evidence cannot qualify under
  environment v2. Semantic diagnosis/correction/independent validation,
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

Hand off W4 + W5 in PR #65 and keep it **unmerged**. No further implementation
is approved in this task. After approval/merge, the recommended next package is
W6a — Semantic Diagnosis, subject to a separate owner instruction; do not begin
W6b corrections or later packages automatically. No paid provider calls,
qualifying Canary or Full40 run is authorized by this batch.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [W0 decision and verification history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
