# PR55 relational semantic validation

Phase 0 passed on `6af16a4eb002b5b1b56619d6fe4b477d799c87bc`.
The [existing validator](../../backend/app/query_engine/semantic_plan.py) retains
Required Intent. New checks consume no question text and introduce no plan schema.

## Guarantees and trusted evidence

- Explicit SUM requires an `integer`, `numeric`, or `decimal` domain column.
  Other/unknown types fail with `sum_target_not_numeric`. COUNT(*) stays fieldless.
- COUNT(DISTINCT *) fails with `count_distinct_target_missing`. SUM DISTINCT is
  explicitly rejected with `sum_distinct_unsupported`, matching the current
  renderer's bounded algebra. Catalog SUM has no target field and fails with
  `metric_sum_target_missing` rather than choosing a field from prose.
- Aggregate field ordering requires a declared GROUP BY key
  (`order_field_not_grouped`). SELECT DISTINCT field ordering also requires that
  field in the output (`distinct_order_field_not_output`). Existing output/group,
  aggregate-reference, and HAVING checks remain authoritative. No functional
  dependency is inferred to allow ungrouped fields.
- The [shared join traversal](../../backend/app/query_engine/relational_semantics.py)
  is the renderer's existing deterministic traversal. Validation rejects
  `left_join_orientation_unsupported` before accepting a tree that cannot be
  rendered with the existing directed LEFT JOIN semantics. This changes no
  candidate, selected path, relationship role, or SQL ordering for accepted trees.
- Declared `many_to_one` is to-one in the forward direction; its inverse can
  multiply rows. Declared `one_to_one` is to-one in both directions. All branches
  of the selected tree matter. These are catalog facts, not uniqueness inferred
  from an identifier or display field. Filters are not assumed to remove fanout.
- Named COUNT metrics declare an entity source. Their COUNT(*) compilation is
  rejected with `metric_population_unsupported` if that source can multiply or
  is null-extended. Selected joins may still restrict the population. This is a
  conservative upper-bound proof, not a guarantee that a selected join matches
  what the user meant. Ad-hoc COUNT(*) continues to count joined rows.
- Metric SQL conformance permits COUNT(field) for COUNT(*) only when that field
  belongs to the metric entity, is non-null in domain metadata, and is not the
  newly added side of a selected LEFT JOIN. A base-table NOT NULL declaration
  alone is insufficient. WHERE-based null rejection is deliberately not inferred.

The existing Required Intent FK/PK COUNT DISTINCT normalization remains unchanged:
it requires selected INNER, nonoptional many-to-one, an actual non-null SQLAlchemy
FK, and an individually unique referenced identity. It never equates COUNT with
COUNT DISTINCT. Ad-hoc SQL conformance remains exact, so no new normalization is
silently applied to Evaluation V2, HAVING, or ordering. The new non-null proof is
query-engine-owned and reusable; no evaluator integration is part of PR55.

## Explicit limitations

Ad-hoc aggregates share the declared joined input relation and grouping keys.
A field target identifies ownership, **not** a promise to sum each source row once.
Thus a SUM over duplicated joined rows remains legal, as do multiple aggregates
from different entities. SUM DISTINCT is not a repair for fanout: equal values
can belong to different source rows. Source-preserving business SUM, independent
measure populations, functional dependencies, and richer source grains cannot
be proved from the current contracts. They remain deferred; optional PR58 may
add narrowly justified metadata. PR55 does not claim to solve those gaps.

COUNT(*) / COUNT(field) equivalence says nothing about distinctness, and SUM on
an empty input is NULL while COUNT is zero. Relationship equality under INNER
does not justify FK/PK substitution under LEFT when a target may be absent or
invisible. Conservative proofs may reject named-metric joins whose safety would
require additional filter, uniqueness, or referential-visibility reasoning.

PR53's omitted outputs, dimensions, detail/total choice, counted subject, HAVING
attachment/value, and ranking remain PR57 interpretation responsibilities.
PR56 owns candidate/path completeness. The [PR53 report](semantic-ownership-migration.md)
and its diagnostic fixtures/results remain frozen with their historical numbering.
Production NL ownership, provider calls/schema, authorization/RLS, templates,
Evaluation V2, scoring/readiness and release thresholds are unchanged.

## Verification

[Synthetic relational tests](../../backend/tests/test_relational_semantics.py)
exercise validation, rendering, safety and conformance. PostgreSQL cases use
transaction-local temporary tables in an explicitly disposable, guarded database;
they prove joined duplicates, one-to-one uniqueness, NULL extension, nullable
counts, empty inputs, grouped/HAVING/order execution and reference-identity
counterexamples. They import neither English fixtures nor Evaluation V2.

Run `./scripts/check` for the ordinary baseline, then the focused tests with
`POSTGRES_TEST_DATABASE_URL` and `POSTGRES_TEST_DATABASE_DISPOSABLE=1` under the
[V3 validation model](validation-model.md). PostgreSQL skips are missing evidence
for these proofs. No provider calls or browser flows are needed.
