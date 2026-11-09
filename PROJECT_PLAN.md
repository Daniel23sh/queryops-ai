# QueryOps AI — Project Plan

## Current Status

Active milestone: **M10 — Product Reliability & V1 Completion**. The target is a
reliable, complete **local IT Operations V1 using synthetic data**. V1 remains
**incomplete and unreleased**. Shared/production deployment, real identity,
additional domains and new major capabilities remain separate future scope.

W0–W5 (including W2a), W6a/W6b, W7 and W8 implementations are merged. W6c
diagnostics and the bounded existence-grounding correction are complete within
their scopes. Merged commits, implementation evidence and limitations are retained
in [development history](docs/history/development-history.md).

[PR #76](https://github.com/Daniel23sh/queryops-ai/pull/76) merged at
`b2519b2909e5b5615f2211afd6c7e4aa74ae09ad`. All six final-main deterministic
jobs passed in [CI run 41907001375](https://github.com/Daniel23sh/queryops-ai/actions/runs/41907001375).
That is an engineering checkpoint, not a frozen release candidate or qualifying
live evidence. This documentation reconciliation must itself merge and the
resulting final `main` must pass CI before any separately authorized freeze.

W6c v3 completed six measured responses with four semantic acceptances. W6C-008
failed its output contract; its multiset was not evaluated. W6C-012 returned
clarification without a plan; its cause is unknown. The merged correction removes
independently reproduced misleading existence-to-aggregation guidance; neither
historical provider failure is proven fixed. Both terminal journals and all frozen
evidence must remain unchanged. No diagnostic result qualifies V1.

## Remaining Decisions and Release Gates

The [W9 entry decisions and handoff](docs/evaluation/w9-entry-decisions.md) propose,
but do not approve:

- Owner acceptance of the two residual W6c limitations **for entering W9 only**.
- Retaining the production live profile (two SDK retries, redirects enabled,
  no enforced physical-dispatch cap), versus a separately authorized hard-bound
  implementation before freeze. Retention is recommended; the owner must choose.
- A later offline freeze/preparation task, followed by separate exact-identity
  live authorization for canary ×3 and, only after stability passes, full40.

All decisions above remain **pending**. Merging this reconciliation does not
accept risk, select a live profile, authorize freeze or authorize paid requests.
No current qualifying V2 canary/full40, automated `ready`, or complete manual QA
has been established. Existing thresholds, zero-defect/security requirements and
same-candidate manual QA remain mandatory under the
[release policy](docs/evaluation/v1-quality-gates.md).

## Next Approved Work

Documentation and release-decision preparation only on
`feature/m10-w9-entry-reconciliation`: reconcile merged status, draft owner choices
and the post-merge handoff, verify references/contracts, obtain independent review
and open a focused **Draft PR against main**. Stop at that reviewed Draft PR;
do not merge.

No product code, dataset/oracle/prompt/threshold change, final freeze,
feature-branch qualification manifest, provider probe, paid Evaluation or
operator-approval file is authorized. Never reset or reuse terminal W6c journals;
never adopt/reset user resources.

After merge, the next step is an owner decision on the pending risk/profile
choices and explicit authorization of **W9 Offline Freeze and Evaluation V2
Preparation**. That task must verify clean latest main and final-main CI, then
follow the [handoff](docs/evaluation/w9-entry-decisions.md#post-merge-handoff).
W10 cleanup remains optional, not an inferred release prerequisite.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [Development history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
- [Manual QA](docs/qa/v1-manual-qa.md)
