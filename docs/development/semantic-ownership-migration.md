# Semantic ownership — PR57 cutover and historical PR53 evidence

## PR57 production boundary

Free queries now follow: question → authorized bounded candidates → one provider
interpretation as SemanticPlan → deterministic validation/compilation/conformance
→ governed execution. Exact lexical matches protect useful candidate context, not
plan obligations. Structural phrase hints populate only Suggested Intent and
cannot veto a plan. Required Intent remains fail-closed but is reserved for a
future independently trusted structured source; PR57 introduces none.

Authorization, projected fields/candidates, selected catalog definitions and their
dependencies, OR-collapse protection, supported algebra, PR55 relational proofs,
unused-entity checks, rendering and SQL conformance remain binding. Only selected
definition dependencies—not lexical matches—can justify conjunctions that would
otherwise collapse a selected OR rule. PR56 relationship completeness and the
16KB deterministic fail-closed projection budget are unchanged. Connector-only
entities still import no unrelated business semantics or examples.

The provider output schema, SemanticPlan, one-call architecture, runtime roles,
V2 assets and readiness policy are unchanged. Legal-plan acceptance is not proof
of correct English interpretation. Live evidence and manual QA remain separately
required; no provider run is authorized. PR58 is not included.

## Versioned diagnostic reruns

The PR53 evidence below records the original experiment, not current production.
Its frozen fixtures and reported results are not rewritten. Current CLI output
is `semantic-ownership-shadow-v2`: historical hint axes and lexical checks around
the **current** deterministic validator. This preserves the recorded fixed-fixture
outcomes but is not an exact historical validator: OR decisions and first-rejection
ordering may differ outside that evidence. Reproduce V1 at its historical source
revision (for example, post-PR53/PR54 main
`6af16a4eb002b5b1b56619d6fe4b477d799c87bc`).

PR52 reruns are explicitly `queryops-v2-structural-conformance-v2-legacy-hints`.
They compare the retained pre-cutover hint axes, not production Required Intent.
The small [offline adapter](../../backend/app/diagnostics/legacy_semantic_grounding.py)
shares hint calculation; it neither copies the parser nor installs a runtime
legacy mode. StructuralResultIntent and its comparisons remain diagnostic-only.

## Decision and experiment boundary

Phase 0 passed against verified main `4263fc5b29dea9d2ff8367cfefd1eb219cab239d`.
PR52 is merged. The approved architecture remains one provider call returning
SemanticPlan, catalog-owned business definitions, deterministic compilation and
validation, and unchanged authorization/RLS. No new executable IR is needed.

PR53 was an offline diagnostic, not the PR57 architecture in production. It
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

Lexical entity, concept, metric, and rule mandates remain separate retained
influences. PR56 replaces single-path pruning with complete authorized
relationship components containing at least two semantic anchors. Connector
entities and relationships are candidates only: they do not add mandatory
evidence or import concepts, metrics, or examples. Selected catalog definitions,
authorized fields, scope restrictions, graph legality, Boolean composition,
type/reference checks, and existing guarded FK/PK normalization are not removed.
Runtime roles, RLS, SQL safety and conformance are outside this experiment and
untouched.

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
| `license_count_value` paraphrases | Exact single-count grounding rejects count plus SUM | PR57 interprets full request; PR55 validates numeric types/shared population |
| `distinct_os`, `subject_*` | COUNT(*) binding rejects distinct-value/entity counts | PR57 chooses subject; PR55 checks declared count/null/multiplicity semantics |
| `two_dimensions` | Group/output inference conflicts with complete requested dimensions | PR57 interprets dimensions; PR55 checks legal declared grain |
| `temporal_only` | One age paraphrase invents HAVING >14; another does not | PR57 attaches language correctly; PR55 checks declared predicate phase/types |
| `ticket_groups_missing`, `device_output_missing` | Legacy catches omitted requested grouping/outputs | PR57 request completeness; no relational proof recovers omitted English |
| `ticket_total_as_detail` | Legacy catches detail rows replacing a requested total | PR57 chooses structure; PR55 checks declared shape |
| `aggregate_threshold_missing` | Legacy catches omitted HAVING | PR57 chooses threshold; PR55 checks references/types, not intended value |
| `user_grain_as_joined_rows` | Legacy catches joined-row count replacing distinct users | PR55 proves declared user grain/fanout where facts suffice; PR57 still selects the subject |

The user-grain counterexample is two same-OS devices for one user: two joined rows
versus one distinct user. This is a relational reasoning example, not a claim that
PR53 executed PostgreSQL or established new grain enforcement.

Both paths also accept omitted SUM, row count replacing distinct OS count, and
reversed ordering. Negation and ambiguous department paths are explicit unknown
controls. This exposes limits that already exist rather than attributing them to
removal. Four controls reject on both paths: unavailable field, inconsistent
group shape, resolved-scope literal, and retained lexical metric mandate.

## Migration checkpoint

PR55 added renderability, aggregate input type, selected-graph multiplicity,
population, and null-sensitive validation where catalog facts can prove them.
The fixtures directly illustrate grain and multiple-aggregate concerns; they do
not establish a new defect in every one of those categories.

PR55 cannot replace every useful lost check. Requested outputs, group completeness,
threshold attachment/value, and ordering are PR57 interpretation responsibilities.
Pretending these are relational facts would recreate the competing parser. Keep
the lost-check evidence visible through PR57; deterministic acceptance alone does
not authorize switching runtime ownership or establish model accuracy.

PR56 owns candidate/path completeness. It retains every authorized relationship
in an anchor-relevant connected component rather than choosing a shortest or
preferred route. Examples are still selected only from direct semantic or lexical
evidence, optional context trims before relationship candidates, and any complete
candidate set that cannot fit the 16KB projection fails closed.

PR57 must align grounding, prompt hierarchy and enforcement atomically. No
currently generated NL-derived structural requirement has an unconditional
reason to stay binding. Independently trusted structured constraints, if
introduced later, would need their own provenance and must not be passed through
this question-derived ablation.

Frozen V2 digest remains
`a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0`.
The recorded PR52 evidence remains unchanged; versioned reruns above neither modify
V2 nor uses its conflict count as a success criterion. Validation/review evidence
is recorded in [development history](../history/development-history.md).
