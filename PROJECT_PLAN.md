# QueryOps AI — Project Plan

## Current Status

PR57 is merged at `75568dc5f6cef5f541eac1b357e8809828133547`.
The independent canary audit authorized an Evaluation V2 correctness correction,
without provider-output inspection or tuning. The correction covers proven grouping
identities, the hard-004 directory-user bridge, and hard-006 savings output/ranking.

Milestones 0–8 and M9 implementation through PR11 are complete. V1 remains
**incomplete, not production-ready, and not released**. Prior live measurements
are non-qualifying for the corrected source/dataset, including the formal
provider run described by the operator as diagnostic evidence.

## Active Objective and Approved Scope

The evaluator-only correction, focused regressions, normal full checks,
disposable PostgreSQL verification, and independent review are complete. Update derived V2 and
canary identities deterministically while retaining dataset ID/version and canary
membership. See [correction evidence](docs/evaluation/v2-semantic-corrections.md).

## Constraints

- No live provider calls, canary, provider-output inspection, or result-driven tuning.
- No production planner/prompt/algebra, authorization, RLS, SQL safety, renderer,
  conformance, historical V1 dataset, or readiness-threshold changes.
- Preserve medium-009; its distinctness-enforcement gap is separate work.
- Changes invalidate prior qualifying evidence. This work does not claim readiness.
- Do not modify ignored planning documents or run tests against user databases.

## Next Approved Work

None after completion of this correction. A later release candidate must be
explicitly frozen and separately authorized before the three-canary/full-run
sequence; full manual QA remains required.

## References

- [Agent instructions](AGENTS.md)
- [Validation model](docs/development/validation-model.md)
- [Release policy](docs/evaluation/v1-quality-gates.md)
- [Readiness report](docs/evaluation/v1-readiness-report.md)
- [Development history](docs/history/development-history.md)
