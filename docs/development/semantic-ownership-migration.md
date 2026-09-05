# PR53 — Offline semantic ownership migration evidence

## Decision and experiment boundary

Phase 0 passed against verified main `4263fc5b29dea9d2ff8367cfefd1eb219cab239d`.
PR52 is merged. The approved architecture remains one provider call returning
SemanticPlan, catalog-owned business definitions, deterministic compilation and
validation, and unchanged authorization/RLS. No new executable IR is needed.

PR53 is an offline diagnostic, not the PR56 architecture in production. It
compares the **same supplied SemanticPlan object** using the existing validator:

- Legacy: the projection produced by current grounding, unchanged.
- Proposed structural binding: a dataclass copy with only
  `grounded_result_intent=None`.

The second path retains lexical entity/concept/metric/rule mandates, authorized
candidates, selected relationship graph, suggestions, catalog definitions,
scope-literal restrictions, and all other validator checks. These retained
NL-derived restrictions are reported, not endorsed as final semantic authority.
Neither path renders SQL, runs conformance, authorizes an actor, executes a query,
connects to a database, calls a provider, or persists results. An acceptance means
only that this validator accepted this supplied plan under fixture context.

## Implementation and reuse

- [Inventory and comparison](../../backend/scripts/semantic_ownership.py)
- [Independent fixtures](../../backend/scripts/semantic_ownership_fixtures.py)
- [CLI](../../backend/scripts/audit_semantic_ownership.py)
- [Focused tests](../../backend/tests/test_semantic_ownership.py)

The inventory is typed, static report data, never production configuration.
Current validator decisions are reused rather than reimplemented. PR52 adapters
and comparison policy supply observed structure and comparison with independently
authored expected structure. No PR52 API changes are necessary. The tiny fixture
schema builder stays separate from PR52's V2-specific context loader to avoid
coupling independent fixtures to Evaluation V2.

From `backend/`:

```bash
.venv/bin/python -m scripts.audit_semantic_ownership
.venv/bin/python -m scripts.audit_semantic_ownership --json
```

Output goes to stdout only. JSON omits question text, plans, SQL, rows, and scope
literals. Question and plan data are hand-authored synthetic fixtures in source.
The report includes fixture IDs, paraphrase indices, first rejection reasons,
structural mismatches, retained mandates/relationships, and future-owner notes.
Unexpected errors propagate rather than being converted to acceptance.

## Authority inventory

The inventory accounts for six authority classes: policy/authorization facts,
catalog business facts, relational facts, NL interpretation, provider guidance,
and diagnostics. The first three remain deterministic; being deterministic code
does not make a lexical interpretation a fact.

NL-derived structural authority covers subject selection, quantity/count,
aggregate target/distinctness, grouping, numeric HAVING attachment, and output
phrase matching. Detail grain is currently suggested only. Required top-level
DISTINCT is representable but currently unset; suggested detail defaults false.
Ordering and limit are not GroundedResultIntent fields. Exact metric matching
suppresses structural grounding and instead imposes the scalar metric contract.

Lexical entity, concept, metric, rule mandates and heuristic path pruning are
separate retained influences. Selected catalog definitions, authorized fields,
scope restrictions, graph legality, Boolean composition, type/reference checks,
and existing guarded FK/PK normalization are not removed. Runtime roles, RLS,
SQL safety and conformance are outside this experiment and untouched.

## Independent evidence

The initial fixture set contains 32 supplied-plan fixtures, 24 distinct question
strings and 39 comparisons including paraphrases and deliberately wrong plans.
It covers counted subject, grouping versus ordering, temporal versus aggregate
thresholds, detail versus aggregate, multiple aggregates, row versus distinct
count, multiple dimensions, relationship ambiguity, negation and order priority.
A tiny laboratory catalog defines sample age at fourteen days without adding
laboratory vocabulary to generic migration logic. No V2 assets are imported by
the scripts and no fixture question equals a V2 question.

Observed outcomes (frozen evidence for this fixture revision, not thresholds):

| Legacy / proposed | Comparisons |
| --- | ---: |
| Accept / accept | 20 |
| Reject / accept | 15 |
| Reject / reject | 4 |
| Accept / reject | 0 |

Of the 15 changed outcomes, 7 are false structural constraints, 7 are useful but
NL-derived checks, and 1 is unresolved. These counts are not quality scores.

Classification is conservative and scoped to the supplied fixture structure:

- **FALSE_CONSTRAINT:** proposed validation succeeds and the plan matches the
  independently declared expected structure.
- **USEFUL_BUT_NL_DERIVED_CHECK:** the supplied structure is wrong, and the removed
  first-rejection component agrees with the independent intended requirement.
- **UNRESOLVED:** expectation is missing/unknown, or a wrong legacy rule happens
  to reject a wrong plan. In `second_dimension_missing`, the latter is observed;
  rejecting any bad plan is not automatically a useful check.
- **REAL_DETERMINISTIC_INVARIANT:** reserved for an unexpected differential
  outside the six structural rejection reasons, or reverse acceptance. No such
  differential occurs; it would require investigation before migration.

PR52 comparison is not an equivalence prover. Its mismatches are descriptive and
do not override current validator normalization. The fixture oracle covers only
explicit structure: predicates and ambiguous relationship roles remain unknown,
not inferred to pass. Both-rejected cases can mask later structural failures;
first-rejection output is not an exhaustive validator trace.

## False constraints and lost checks

| Evidence | Finding | Future responsibility |
| --- | --- | --- |
| `license_count_value` paraphrases | Exact single-count grounding rejects count plus SUM | PR56 interprets full request; PR54 validates numeric types/shared population |
| `distinct_os`, `subject_*` | COUNT(*) binding rejects distinct-value/entity counts | PR56 chooses subject; PR54 checks declared count/null/multiplicity semantics |
| `two_dimensions` | Group/output inference conflicts with complete requested dimensions | PR56 interprets dimensions; PR54 checks legal declared grain |
| `temporal_only` | One age paraphrase invents HAVING >14; another does not | PR56 attaches language correctly; PR54 checks declared predicate phase/types |
| `ticket_groups_missing`, `device_output_missing` | Legacy catches omitted requested grouping/outputs | PR56 request completeness; no relational proof recovers omitted English |
| `ticket_total_as_detail` | Legacy catches detail rows replacing a requested total | PR56 chooses structure; PR54 checks declared shape |
| `aggregate_threshold_missing` | Legacy catches omitted HAVING | PR56 chooses threshold; PR54 checks references/types, not intended value |
| `user_grain_as_joined_rows` | Legacy catches joined-row count replacing distinct users | PR54 needs declared user grain and fanout proof; PR56 still selects the subject |

The user-grain counterexample is two same-OS devices for one user: two joined rows
versus one distinct user. This is a relational reasoning example, not a claim that
PR53 executed PostgreSQL or established new grain enforcement.

Both paths also accept omitted SUM, row count replacing distinct OS count, and
reversed ordering. Negation and ambiguous department paths are explicit unknown
controls. This exposes limits that already exist rather than attributing them to
removal. Four controls reject on both paths: unavailable field, inconsistent
group shape, resolved-scope literal, and retained lexical metric mandate.

## Migration checkpoint

PR54 should prove renderability, aggregate input types, declared grain/fanout,
compatible aggregation populations, and null-sensitive equivalence. The fixtures
directly illustrate grain and multiple-aggregate concerns; they do not establish
a new defect in every one of those categories. SQL compilation and PostgreSQL
tests belong to the separately approved implementation phase for those proofs.

PR54 cannot replace every useful lost check. Requested outputs, group completeness,
threshold attachment/value, and ordering are PR56 interpretation responsibilities.
Pretending these are relational facts would recreate the competing parser. Keep
the lost-check evidence visible through PR56; deterministic acceptance alone does
not authorize switching runtime ownership or establish model accuracy.

PR55 owns candidate/path completeness. PR56 must align grounding, prompt hierarchy
and enforcement atomically. No currently generated NL-derived structural
requirement has an unconditional reason to stay binding. Independently trusted
structured constraints, if introduced later, would need their own provenance and
must not be passed through this question-derived ablation.

Frozen V2 digest remains
`a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0`.
The PR52 audit remains unchanged and reproducible; this report neither modifies
V2 nor uses its conflict count as a success criterion. Validation/review evidence
is recorded in [development history](../history/development-history.md).
