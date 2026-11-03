# Bounded reverse-preserving LEFT joins

M10 W6c F1 extends the structured SemanticPlan relationship intent with one
explicit value. The provider still returns a single structured plan; only the
backend validates it, owns SQL rendering, checks conformance and executes it.

| `join_type` | Preserved endpoint | Newly added endpoint | SQL |
| --- | --- | --- | --- |
| `inner` | Neither guaranteed | Either endpoint | `INNER JOIN` |
| `left` | `from_entity` | `to_entity` (nullable) | `LEFT JOIN` |
| `left_reverse` | `to_entity` | `from_entity` (nullable) | `LEFT JOIN` |

For the catalog relationship from `security_events.user_id` to
`directory_users.id`, the following explicit intent renders
`FROM directory_users LEFT JOIN security_events ON security_events.user_id = directory_users.id`
when it is the only selected edge:

```json
{"relationship_id": "security_event_user", "join_type": "left_reverse"}
```

## Compatibility and enforcement

The existing sorted-root/sorted-edge traversal and equality rendering are
unchanged for plans containing only `inner` and `left`. New intents traverse only
from their preserved endpoint to the other endpoint. A connected acyclic tree
without a compatible root still fails `left_join_orientation_unsupported`.
Validation and rendering share the bounded traversal. No relationship is
invented, duplicated, aliased or selected on behalf of the provider. Legacy
`left` plans are never automatically reversed.

The Pydantic enum and field description are part of the provider-facing
structured schema. Catalog example parsing accepts the same values; the actual
catalog and its examples remain unchanged. Plan observations retain the exact
intent in `relationship_join_types`. Conformance compares the physical SQL LEFT
join and actual newly joined nullable entity against the endpoint specified by
the plan. Reversing the preserved SQL side fails
`semantic_relationship_mismatch` even when the equality is identical.

Physical LEFT ON clauses accept only the selected relationship equality.
Residual ON filters fail `semantic_sql_shape_unsupported`: moving an independent
WHERE restriction into LEFT ON can broaden the preserved population. This closes
a pre-existing conformance gap for both LEFT orientations; canonical legacy
rendering is unchanged. INNER residual-filter normalization is unchanged.

Grouped composition-rule OR predicates and independent conjunctive restrictions
retain their existing WHERE expressions. Join predicates remain catalog
equalities. No optional branch predicate is promoted to a mandatory conjunct.
Callers must select LEFT intents along every optional path they want preserved;
a later INNER join or explicit independent filter may still restrict rows.

Both LEFT intents null-extend the added entity. Base NOT NULL metadata does not
prove that entity's input fields non-null. Named COUNT metrics reject either
null-extension of their population or possible fanout. Cardinality is still
interpreted from the catalog direction. DISTINCT, COUNT(*)/COUNT(field)/
COUNT(DISTINCT field), numeric SUM, GROUP BY, HAVING and ordering retain their
contracts. FK/PK substitution remains limited to proven selected INNER
relationships in required-intent checks and downstream Evaluation observations.

Resources, columns and relationship endpoints must remain eligible under current
effective permissions and exact assigned scopes. Execution retains sanitized
read-only SQL, bounded limits, the non-owner `queryops_query_runtime` role and
transaction-local PostgreSQL RLS context.

## PostgreSQL regression evidence

Permanent tests do not import or modify the frozen audit fixtures:

- [Relational tests](../../backend/tests/test_relational_semantics.py) cover all
  three intents, byte-exact legacy SQL, wrong-side rejection, non-null proofs,
  conflicting orientations, invalid/malicious selections, deterministic ordering,
  cardinality and named-metric guards. On the same synthetic relation:

  | Intent | COUNT(*) | COUNT(parent.id) | COUNT(DISTINCT parent.id) | SUM(parent.amount) | SUM(child.amount) |
  | --- | --- | --- | --- | --- | --- |
  | `inner` | 2 | 2 | 1 | 20 | 5 |
  | `left` | 3 | 2 | 1 | 20 | 9 |
  | `left_reverse` | 3 | 3 | 2 | 20 | 5 |

- [Governed API tests](../../backend/tests/test_reverse_left_postgres.py) use a
  fake OpenAI Responses parser and real plan validation, SQL rendering, safety,
  conformance, persistence and PostgreSQL execution. A synthetic population has
  branch-A-only, branch-B-only, both, neither, nonqualifying witnesses, NULL
  references, independent-filter counterexamples and out-of-scope witnesses.
  An independent EXISTS oracle under RLS returns exactly the same **three users**
  as the reverse-LEFT plan. Without DISTINCT there are eight rows (2 + 2 + 2×2);
  COUNT DISTINCT returns three and COUNT(event.id) six. Legacy supported
  INNER/LEFT plans still return only the both-branches user for this query.
  Hidden optional witnesses appear as NULL and cannot qualify visible users.
  Scope/permission/resource/column denials prevent execution; changing affiliation
  does not change the assigned scope. SQL drift that requires an optional branch
  or weakens the independent AND is rejected before execution.
- Catalog example parsing, required-intent FK/PK normalization and Evaluation
  observation identity checks explicitly cover the new value.
- [PostgreSQL CI](../../.github/workflows/ci.yml) runs the complete backend suite,
  asserts zero skips and asserts selection of the new API regressions from JUnit.

## Remaining limits

This remains the bounded join-tree algebra. It adds no RIGHT/FULL join,
EXISTS/UNION plan node, repeated entity/relationship alias, reverse catalog edge,
new business-filter expression, source-preserving SUM or fanout inference from
filters. Ad-hoc aggregates operate on the declared joined relation; DISTINCT
must be selected explicitly for the intended output grain. Named-metric proofs
remain conservative.

The [F1 investigation](../audits/2026-11-02-w6c-offline-validation-he.md) and
`docs/audits/w6c/` evidence at `04834e5` remain frozen historical evidence. The
branch starts from latest main `761ddb2`, which already contained PR #69 before
this task. This implementation does not alter or merge that PR.

Supplied plans and fake transport establish backend contract behavior; they do
**not** measure natural-language interpretation or provider accuracy. No paid
calls, W6c Live, model/prompt tuning, frozen Evaluation changes or release
qualification are included.

## Local V3 validation (2026-11-02)

Dedicated loopback-only PostgreSQL 16 ran in the disposable `queryops_f1_test`
database, with the repository's destructive-test opt-in and endpoint/name guards.
The CI-equivalent selections passed **2,007 backend tests + 20 action release
tests**, with zero failures/errors/skips. JUnit confirms all **13** new governed
API cases executed. Ruff (`app`, `scripts` and changed tests), Pyright and Python
compilation passed. Alembic upgrade/current/check confirms head
`0010_disable_inactive_user` and no ORM schema diff. Markdown targets, diff
whitespace and unchanged frozen audit inputs were checked separately.

Fresh-context independent V3 review found the LEFT ON/WHERE placement gap above.
It was corrected and re-reviewed with no remaining findings. The reviewer ran
77 focused tests and verified the corrected 127-test PostgreSQL/API/conformance
selection, all passing without skips.

No frontend implementation changed. Governed end-to-end evidence is the real
HTTP API/auth/session/CSRF/plan/SQL/PostgreSQL path with an in-process fake OpenAI
transport; browser/visual tests and live-provider interpretation are not claimed.
