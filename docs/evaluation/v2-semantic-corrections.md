# Evaluation V2 semantic correctness correction

Based on audited revision `75568dc5f6cef5f541eac1b357e8809828133547`.
The checkout matched exactly before editing. Only evaluator behavior and V2 data
change; no provider outputs or existing evaluation runs informed the correction.

## Semantic changes

- Grouping equivalence uses non-null, single-column primary/unique constraints
  from authoritative ORM metadata and selected catalog FK equalities. Only
  selected INNER joins provide equal-value evidence. Outer, disjunctive,
  unselected, and unproved relationships provide no such evidence.
- A unique key determines other columns of the same table row, so adding such a
  column cannot split a group. This does not infer arbitrary dependencies across
  tables, accept extra population dimensions, or infer single-column uniqueness
  from composite constraints.
- Required output values remain binding. Distinct unique keys can identify the
  same grain without having equal values. Semantic scoring requires a projected
  group identity; result comparison requires a shared, validated identity column
  and checks its values plus every required measure.
- `itops-medium-006` no longer requires department-name presentation. Its baseline
  supplies ID and name as alternative shared identity evidence. ID-only,
  name-only, and ID-plus-name representations are accepted. Extra user-status
  grouping, missing identities, wrong IDs, and missing explicitly required
  outputs remain failures.
- `itops-hard-004` baseline and expected resource metadata use the existing
  `login_event_user` / `user_group_membership_user` bridge through directory users.
  Both equivalent user keys are accepted. Privileged membership, failed events
  within 30 days, distinct event count and HAVING count greater than five remain
  binding. No relationship or plan capability was added.
- `itops-hard-006` removes reclaim count from both contract and baseline. Population,
  product-name grain, non-distinct cost SUM and descending savings order remain.
  Result comparison checks actual lexicographic ranking and compares rows within
  exact baseline ties without imposing unrequested tie-breaks. Numeric value
  tolerance remains intact; nearby unequal values are not treated as ranking ties.

All normalization lives under `app/evaluation`; production query-engine validation,
SQL safety, authorization, RLS, rendering and conformance are unchanged. Historical
V1 has no semantic contract and retains its existing result comparison behavior.
The structural intent comparator remains a literal, opt-in structural diagnostic;
it is not the authority for evaluator relational equivalence.

## Identity transition

Dataset ID/version remains `it_operations_v2` / `2`; the fixed canary ID/version
and its ten members remain unchanged. Existing invariants require no version bump.

| Identity | Before | After |
| --- | --- | --- |
| V2 dataset | `a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0` | `372a5c203fb86e176f207656846884b8d5df5a1e939501e5ec9a35f65da2fe5e` |
| Canary | `d07a3a67542d68af1828933d4519e1f9e2ece51b38571831b35883a1ff742e32` | `c4fac0491cbd576d47d38722d7c45b3be6562a187c0324758ea98ce19a74a389` |

Prior source/dataset evidence cannot qualify the corrected candidate. The operator's
formal provider run remains diagnostic only; it was not inspected. No readiness
claim or live canary is part of this correction. Historical documents retain their
original identities explicitly as historical evidence, not current freeze values.

## Verification

Focused synthetic regressions cover equivalent and different grains, required
outputs, selected-inner-join proof boundaries, SUM/count/HAVING, exact ties,
incorrect ranking, numeric tolerance, and deterministic dataset/canary digests.
PostgreSQL regressions execute all three corrected baselines and alternative
representations under the existing governed runtime and RLS. A synthetic fixture
checks six versus five failed logins with two privileged memberships per user,
plus excluded old events and successful logins. All DB work uses a newly created,
isolated disposable PostgreSQL 16 instance, never an existing database.

Final full-suite and independent-review results are recorded in
[development history](../history/development-history.md).

## Separate concerns

The medium-009 distinctness-enforcement gap remains unchanged. Product-name grain
in hard-006 remains as instructed; vendor/product identity disambiguation requires
separate dataset review. Neither concern is silently expanded into this fix.

## Files changed

- Dataset: `backend/app/domains/it_operations/domain_pack/evaluation_questions_v2.yaml`.
- Evaluator: `backend/app/evaluation/identity.py`, `contracts.py`, `provenance.py`,
  `scoring.py`, and `selection.py`.
- Tests: `backend/tests/test_evaluation_semantic_corrections.py`,
  `test_evaluation_runner_postgres.py`, and `test_evaluation_dataset.py`.
- State/evidence: `PROJECT_PLAN.md`, this report, `v1-quality-gates.md`,
  `m9-pr11-implementation-report.md`, `v1-readiness-report.md`,
  `docs/development/semantic-ownership-migration.md`, and
  `docs/history/development-history.md`.
