# QueryOps AI — Project Plan

## Current Status

The bounded-result evidence correction is implemented from audited main
`a64d1fa9ebae3abf2a9cd87d27fa0f47e29b1c94`. Production delivery remains subject
to its existing safety cap while evaluator-owned, resource-bounded evidence can
establish the underlying answer population on one shared authorized snapshot.

Milestones 0–8 and M9 implementation through PR11 are complete. V1 remains
**incomplete, not production-ready, and not released**. Prior live measurements
are non-qualifying for the corrected source/dataset, including the formal
provider run described by the operator as diagnostic evidence.

## Active Objective and Approved Scope

Implementation, offline and isolated-PostgreSQL verification, and the final
focused independent review of the bounded-result correction are complete. The
dataset ID/version and canary membership stay fixed while their
structured-contract digests change deterministically. See the
[bounded-result evidence contract](docs/evaluation/bounded-result-evidence.md).

## Constraints

- No live provider calls, canary, provider-output inspection, or result-driven tuning.
- No production planner/prompt/algebra, authorization, RLS, renderer, conformance,
  historical V1 dataset, or readiness-threshold changes.
- Preserve medium-009 provider semantic reliability/composition interpretation,
  hard-004 aggregate-grouping provider/runtime behavior, and other separately
  tracked DISTINCT gaps as independent release blockers.
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
