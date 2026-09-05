# Semantic intent foundation

PR52 Chunk 2 adds an internal structural representation without connecting it to
execution, grounding, prompts, SQL rendering, conformance enforcement, scoring,
or readiness. Its diagnostic source baseline is
`9eb094ab14d8ae5ef05e5a0d5a52cb8ce13287af`.

## Representation and ownership

[`StructuralResultIntent`](../../backend/app/query_engine/structural_intent.py)
belongs to the query engine. It describes row grain, ordinary output fields,
aggregate declarations, GROUP BY, HAVING, ordering, and top-level DISTINCT.
It contains no matching policy or authorization evidence.

Each component uses `StructuralValue[T]`:

- `known` includes a value, including an explicitly empty tuple or `False`.
- `unknown` has no value because the source cannot establish it.
- `unspecified` has no value because the source makes no declaration.

`StructuralRowGrain` represents detail, grouped, or scalar shape. Identity fields
have their own presence state. Scalar grain has an explicitly empty identity.
Partial declarations are retained, not repaired to agree with other components.
In particular, grain requirements and output requirements need not be identical.

The implementation imports the existing `SemanticFieldRef`,
`SemanticAggregationIntent`, and `SemanticOrderIntent` definitions from
[`semantic_plan.py`](../../backend/app/query_engine/semantic_plan.py). They were
not extracted, edited, or replaced. This retains existing imports, schemas,
validators, and serialization. A future integration must address dependency
direction before making `semantic_plan.py` import this foundation.

Field identities contain `entity_id` and `column`, never physical table names.
HAVING uses finite `Decimal` values. Aggregation IDs are local references;
comparison resolves them to function, target field, and aggregate DISTINCT.

## Adapter boundaries

[`structural_intent_adapters.py`](../../backend/app/query_engine/structural_intent_adapters.py)
provides two pure query-engine adapters:

- Grounded intent maps tables through the supplied catalog. Missing or ambiguous
  mappings raise a bounded error. Empty legacy collections become unspecified;
  required output fields use subset comparison, while specified aggregates,
  grouping, and HAVING use exact comparison. Optional DISTINCT is preserved and
  ordering remains unspecified. The caller must identify required versus
  suggested intent; comparison refuses to enforce a suggested requirement.
- Validated plans expose their declared structure. Grouped shape uses GROUP BY
  keys; detail shape retains unknown identity keys. Explicit aggregation without
  grouping proves scalar shape. Named metrics also prove scalar shape; their
  explicit aggregation declarations remain known empty. The adapter never
  fabricates an aggregate expression from the metric. Thus a named metric does
  not satisfy an explicit V2 aggregate requirement. Empty plan collections remain
  known empty.

Neither adapter performs authorization, executes SQL, proves row uniqueness, or
changes existing observation serialization. A validated plan is an internal
input contract, not a replacement for validation of untrusted provider data.

The narrow
[`evaluation adapter`](../../backend/app/evaluation/structural_intent_adapter.py)
maps only existing V2 structural declarations. Concepts, metric identity,
composition rules, semantic source, and answerability remain evaluation concerns.
Non-answerable contracts return no structural requirement. Empty contract
collections are retained as known empty but ignored by V2 policy. No expectation
is inferred from question text or baseline SQL, including top-level DISTINCT.

## Comparison policy

[`StructuralComparisonPolicy`](../../backend/app/query_engine/structural_intent_comparison.py)
is separate from canonical semantics. It supports exact collection comparison,
required subsets, ordered prefixes, and ignored components.

| Component | Grounded requirement | Existing V2 policy |
| --- | --- | --- |
| Ordinary outputs | Required subset | Required subset |
| Aggregations | Exact multiset if specified | Required identity subset |
| GROUP BY | Exact set if specified | Exact set if specified |
| HAVING | Exact set if specified | Required subset |
| Ordering | Ignored | Required ordered prefix |
| DISTINCT | Exact if specified | Ignored |
| Detail grain | Identity fields must be projected | Identity fields must be projected |
| Grouped grain | Exact identity set | Exact identity set |

Detail subset comparison checks projected keys after checking detail shape; it
does not turn unknown observed identity into a proof of uniqueness. Exact grain
comparison retains unknown identity as an unknown result. Missing observations
never become passes. Enforcing an unspecified expectation is a policy error.
An entirely ignored comparison has no pass verdict. Business-semantic scoring is
not included, so this comparison is not a replacement for the existing scorer.

COUNT(*), COUNT(field), COUNT(DISTINCT field), and top-level DISTINCT remain
separate. There are no FK/PK identity equivalences. Existing runtime normalization
and SQL conformance remain untouched.

## Verification and next boundary

Focused tests cover presence, model bounds, immutable inputs, references, mapping,
shape, numeric precision, policies, and dependency direction. Existing provider
tests use local stubs. No PostgreSQL-dependent behavior is modified.

## Offline V2 structural-conformance audit

Chunk 3 adds
[`structural_conformance.py`](../../backend/app/evaluation/structural_conformance.py)
and an offline
[`audit CLI`](../../backend/scripts/audit_structural_conformance.py). The harness
loads the unchanged V2 dataset and real domain pack, projects the allowlisted
queryable domain schema in memory, and builds one current grounding projection
for every case. Synthetic context contains only scope type, global-scope status,
and whether the declared scope mode resolves a reference. It contains no user or
scope identity. It does not use a database.

For non-answerable cases, the projection is still constructed but the structural
report is not applicable. Answerable cases retain separate required and suggested
axes. Compatibility records whether populated required grounding makes the V2
requirement impossible. Coverage independently records how much of the V2
requirement is represented. Missing output subsets can be combined and therefore
are not conflicts. Exact aggregation, grouped-grain, GROUP BY, and HAVING
requirements conflict only when both cannot hold in one plan.
Detail grain also conflicts conservatively with a required exact nonempty
aggregation or GROUP BY, even if required grounding leaves its row-grain field
unspecified; the forcing component carries the conflict while its coverage remains
not applicable to the V2 component.

Each component records compatibility relation and coverage relation separately, so
partial overlap can coexist with a provable exactness conflict. Relations include
exact, covered, partially covered, missing, unspecified, conflict, unavailable,
unsupported by the current grounding model, and not applicable. Ordering is
unsupported because `GroundedResultIntent`
cannot express it. Top-level DISTINCT is representable, although frozen V2
contracts currently make no binding DISTINCT declaration. Known empty contract
collections remain present but their existing ignored V2 policies do not create
requirements.

The existing FK/PK COUNT DISTINCT normalization is not reused: it requires a
validated plan and its selected relationship graph. This offline audit observes
grounding before a plan exists, so applying that rule would invent evidence. The
report identifies that no normalization was reused.

The capability matrix is limited to answerable free queries and derives from
frozen contract structure, `requires_join`, metric/rule declarations, and the
explicit word `distinct` for the one detail case whose contract lacks a DISTINCT
field. It does not use difficulty labels or define thresholds. Template-query
results remain in the all-answerable summary but never enter the free-query
capability matrix.

The CLI prints a concise summary by default and deterministic JSON with `--json`.
It writes nothing unless ordinary shell output is explicitly redirected. The
report contains bounded canonical identities and counts; it omits questions,
prompts, schemas, SQL, rows, user context, provider data, and release verdicts.
It has no dependency on the evaluation runner, baseline executor, scoring,
readiness, provider, database, renderer, or SQL-conformance paths.

Required and suggested mapping failures are isolated: a failure on one axis never
erases the other, and only the required axis determines compatibility.

The first report is diagnostic evidence. Its compatibility labels do not classify
provider ownership, product bugs, or suspect contracts, and it does not authorize
changes to grounding or frozen V2 assets.

## Frozen free-query findings

The first audit covers all 29 answerable free-query cases. Required grounding is
compatible in 23 cases and has a provable conflict in 6; no case is unavailable.
Required coverage is complete for 1 case, partial for 6, absent for 21, and
structurally not applicable for 1. Suggested coverage is complete for 0 cases,
partial for 2, absent for 26, and structurally not applicable for 1. Ordering is
unavailable in the legacy `GroundedResultIntent` model for 4 cases.

The six required-grounding conflicts are:

- `itops-medium-004`
- `itops-medium-006`
- `itops-medium-008`
- `itops-medium-012`
- `itops-hard-003`
- `itops-hard-010`

These cases are evidence of related architectural mechanisms, not six independent
bugs. Review identified five mechanism classes:

A. structural subject and entity binding
B. incomplete multi-aggregation grounding under exact runtime enforcement
C. multi-field grouping limitations
D. COUNT expression identity and the absence of an approved equivalence
E. ambiguity between grouping “by” and ranking or ordering “by”

These classifications are architecture-review findings. They are not Evaluation
V2 tuning rules and do not authorize contract or dataset changes.

## Next-phase invariant

Required structural grounding must be proof-based. If the grounder cannot
deterministically establish a structural interpretation, it must leave that
requirement unspecified instead of emitting a potentially incorrect mandatory
requirement.

The primary safety objective for the next PR is to reduce provable required
structural conflicts among answerable free-query V2 cases from 6 to 0. This does
not require complete grounding for every V2 case. Expanding structural coverage
is a separate later objective.
