# QueryOps AI — Project Plan

## Current Status

Active milestone: **M10 — Product Reliability & V1 Completion**. The target is a
reliable, complete **local IT Operations V1 using synthetic data**. Shared or
production deployment, real identity integration, additional domains and new
major capabilities are separate future scope.

The modular architecture, plan-only provider, deterministic SQL, PostgreSQL RLS,
explicit scopes and governed actions remain the design. The
[2026-10-26 audit](docs/audits/2026-10-26-project-audit-he.md) found substantial
working functionality and reproducible defects; passing tests and historical
milestones do not establish release readiness. V1 is **incomplete and unreleased**.

Remote `main` was verified at `a64d1fa`. W0 selected **retain with narrow
corrections before integration** for `fix/m9-bounded-result-evaluation`.
The original implementation is preserved at
`codex/archive-m9-bounded-result-2d7796c`. Corrections and independent reviews are
complete; GitHub CI and integration remain pending. This is not release qualification.

## Active Objective and Approved Scope

**W0 — Baseline Resolution** is completing verification and integration. The
selected design preserves bounded same-snapshot evidence, with fixes for table-only
authorization metadata, supported input-limit exhaustion, matching top-N answers,
three-run incomplete UI state, and malformed persisted shapes. No unrelated M10
implementation is included. Complete safe GitHub CI/integration, then record the
actual baseline and activate W1. See the decision and evidence in
[development history](docs/history/development-history.md).

Use the [M10 completion roadmap](docs/development/m10-completion-roadmap.md) for
work-package scope, dependencies, acceptance criteria and Definition of Done.
That document supersedes automatic continuation of historical milestone plans;
this file remains the authority for current status and approved next work.

## Constraints

- No unrelated W1–W9 fixes during W0 unless needed for safe baseline integration.
- Preserve authorization, RLS, safety caps, semantic correctness criteria,
  historical V1 baselines and release thresholds. No result-driven dataset tuning.
- Mock is the normal default. Qualifying paid evidence requires a frozen candidate
  and exact model/run authorization; W0 does not need an expensive release sequence.
- Use disposable databases only for state-changing validation; preserve existing
  user work and protect unique branch work before destructive replacement.
- Audit evidence is diagnostic, not qualifying release evidence. Scope, role-request
  races, scoped Evaluation reads, partial delivery, visualizations and semantic
  reliability remain open until individually fixed and verified.

## Next Approved Work

After W0 establishes the baseline: **W1 — Dashboard Exact-Scope Authorization**.
Remove department-affiliation authorization fallbacks; enforce effective
permissions plus explicit assigned scopes across dashboard and card surfaces.
Verify revocation, assigned secondary/global scopes, current-viewer refresh/export
and matching UI capabilities with PostgreSQL and browser regressions. W0 may
identify a justified prerequisite; record it explicitly rather than silently
expanding implementation scope.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
- [Development history](docs/history/development-history.md)
