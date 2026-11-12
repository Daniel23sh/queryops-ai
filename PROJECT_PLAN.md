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

## Current Planner Study Status

PR #82 merged at `a7779b8fa5d7c9aaee0c3170b54be46dbfcbc13e`. The authorized
32-call study completed with both profiles scoring 10/16 and verdict `retain_low`.
Its canonical claim is consumed and permanent. The retained observations cannot
recover actual plans or distinguish clarification from accepted-plan mismatch.
This diagnostic does not qualify V1. Existing study and W9/W6c evidence remain
unchanged.

## Next Approved Work

Add the smallest justified [diagnostic observation and comparison controls](docs/development/planner-diagnostic-observability.md),
reusing the existing scorer/ledger without changing production interpretation,
strict scores or historical evidence. Require independent correctness and
necessity reviews, offline/fake-provider and disposable PostgreSQL evidence, and
all six CI gates. Stop at one focused Draft PR; do not merge. No real provider
request, study replay, guidance change or qualification run is authorized.

## References

- [Agent instructions](AGENTS.md)
- [M10 roadmap and Definition of Done](docs/development/m10-completion-roadmap.md)
- [Development history](docs/history/development-history.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness evidence](docs/evaluation/v1-readiness-report.md)
- [Manual QA](docs/qa/v1-manual-qa.md)
