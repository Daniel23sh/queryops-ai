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

**W1 — Dashboard Exact-Scope Authorization** is the next approved implementation.
Remove department-affiliation authorization fallbacks from shared policy and every
caller; authorize using current effective permissions and exact assigned scopes.
Keep department affiliation as domain/display metadata and preserve personal
ownership and explicit global assignment contracts.

Acceptance: a permission-bearing user whose assignments are revoked loses
catalog/library/detail/source/create/save/duplicate/update/archive/card access;
explicit secondary-department/global assignments still work. Current-viewer
refresh/export never expands authority. API capabilities and browser denial agree.
Use disposable PostgreSQL regressions, focused frontend/browser checks and an
independent V3 review. No unrelated Role/Evaluation/provider fix is part of W1.

## Constraints and Remaining Work

- Follow the [M10 roadmap](docs/development/m10-completion-roadmap.md) for W2–W9
  dependencies/acceptance; W10 cleanup is optional. W6a diagnosis, W6b targeted
  correction and W6c independent validation are separate packages.
- Scope revocation, role-request races, scoped Evaluation JSON DISTINCT reads,
  derived card/CSV delivery disclosure, editor/visualization defects, semantic
  reliability and complete provider/config identity remain open until verified.
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

Implement W1 only. Later packages are the approved direction, not permission to
batch unrelated fixes into the next PR. Any prerequisite changing this order must
be supported by evidence and recorded explicitly.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [W0 decision and verification history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
