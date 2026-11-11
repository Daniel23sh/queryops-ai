# Planner diagnostic observations

The local [planner study harness](planner-reliability-study.md) retains additive
diagnostics in its existing SQLite `slots.result` JSON. This is instrumentation
for future separately authorized diagnostics, not a new experiment or permission
to replay the consumed study. Historical ledgers and scores remain unchanged.
Legacy observations without `diagnostics` have unknown diagnostic detail.

The original `stage`, strict accepted-plan matcher, assessment, advancement
thresholds and terminal failures remain scoring authority. The additive record
has version `1` and contains only these bounded fields:

| Field | Meaning |
| --- | --- |
| `outcome` | `plan`, `clarification`, `unsafe_request` or `provider_failure`. |
| `clarification_reason` | Existing wire reason code, `unestablished` for an unknown reason, or null. No provider text. |
| `plan_comparison` | `strict_match`, `equivalent`, `unestablished` or `not_evaluated`. |
| `mismatch_axes` | Fixed structural categories, including missing, changed or extra predicates. No field names, literals or plan snapshots. |
| `result_multiset_match` | Boolean only when output identities align; otherwise `not_evaluated`. Uses already executed rows. |

The existing stage distinguishes invalid plans, renderer/safety/conformance and
execution failures. Combined with `outcome`, it now separates clarification from
an executed plan mismatch. An `equivalent` plan with matching results can identify
a representation-only miss while its original stage remains `interpretation`.
Neither this field nor matching rows promotes a score to pass.

## Bounded comparison

The [diagnostic helper](../../backend/scripts/planner_study_diagnostics.py) compares
validated plans, without question parsing, SQL execution or provider calls. It
recognizes singleton `IN` versus equality, redundant identical predicates, and
distinct-count targets with proven FK/PK equality in the same selected INNER
graph. It reuses evaluator `IdentityProof` and existing ORM FK/unique-key proof.
All other semantic dimensions must agree, including top-level DISTINCT and
ordering, which the original fixture matcher intentionally treats differently.
HAVING and aggregate ordering also retain their ID-to-expression bindings;
renaming those references is outside this small proof envelope.

Unsupported differences remain `unestablished`, not proven non-equivalent.
`strict_match` means only that the unchanged fixture matcher accepted; it is not
a general equivalence claim. Mismatch categories can still disclose dimensions
omitted by that matcher. Clarification and failures before plan comparison retain
`not_evaluated`. Comparison uses the first declared equivalent fixture form when
no accepted form can be proved equivalent; categories are contract-relative.

Result comparison is independent. Columns align by field and aggregate identities,
never matching values or equal scalar shapes. Different COUNT targets/DISTINCT,
ambiguous outputs and missing identities cannot be compared. The bounded INNER
equality can align the demonstrated distinct FK/PK count. LEFT joins provide no
such proof. Matching samples do not establish semantic equivalence; an unresolved
plan can independently have matching or different comparable rows.

The ledger rejects unknown diagnostic keys, categories and unbounded content
before persistence. No raw plan, SQL, rows, question, provider payload, literal,
identity, scope key or credential is added. No production API or Query Engine
path imports this helper. Grounding, catalog, glossary, prompts, plan validation,
runtime roles/RLS and fixed release contracts are unchanged.

## Offline controls

Run from `backend/`:

```bash
.venv/bin/pytest tests/test_planner_study.py tests/test_planner_study_diagnostics.py tests/test_planner_study_activation.py -q
```

Independent supplied-plan controls cover canonical/equivalent forms, wrong policy
and count choices, nondistinguishing rows, missing outputs, extra grouping,
nullable counts, LEFT joins, changed DISTINCT/order/limit and bounded persistence.
Fake providers cover malformed responses and finite clarification reasons.

The existing explicit `tests/planner_study_live_postgres.py` check additionally
executes ten canonical/equivalent/wrong controls and persists their diagnostics,
with a qualifying hidden-scope group guarding the aggregate count. It runs only
on a newly migrated, owned disposable database using the existing documented
test variables. CI's unchanged PostgreSQL Security job runs that check. Never use
the prepared study or application database. All requests are fake.
