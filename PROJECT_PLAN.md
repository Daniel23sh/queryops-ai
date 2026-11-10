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

W9 froze `46ea556798230d95901045cbe73a5d76981e8c9e` after all six
final-main jobs passed in [CI run 42601895955](https://github.com/Daniel23sh/queryops-ai/actions/runs/42601895955).
The first W9 canary failed qualification and the sequence stopped. Preserve its
environment, manifest and evidence along with both terminal W6c journals.
PR #78 merged the independent temporal Suggested Intent correction. Its effect
on W9 is unmeasured, and the joined-row count hint remains a separate finding.

## Remaining Decisions and Release Gates

The [release policy](docs/evaluation/v1-quality-gates.md) still requires matching
V2 canary stability, full40, automated `ready` and same-candidate manual QA.
Any new freeze, preparation or live qualification requires separate authorization.

## Next Approved Work

Prepare the [offline planner reliability study](docs/development/planner-reliability-study.md)
comparing Terra low and medium reasoning. The approved endpoint is an independently
reviewed Draft PR with deterministic validation. Live study execution and any new
qualification require separate authorization.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [Development history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
- [Manual QA](docs/qa/v1-manual-qa.md)
