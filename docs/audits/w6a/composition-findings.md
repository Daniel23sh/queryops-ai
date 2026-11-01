# W6a composition and output delivery diagnosis

Investigation only. The [probe](composition_probe.py) and
[machine evidence](composition-results.json) use handwritten SemanticPlan fixtures,
not model answers. No provider is called. The existing Mock provider is constructed
by the service but its generation method is not invoked; the diagnostic replaces
`PlanGenerator.generate_plan` with a supplied fixture. This does not test LLM
selection, prompt effectiveness, or current configured model quality.

The frozen runtime is `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`.
The investigation HEAD and the exact [baseline file](baseline.json) hash are
recorded separately. The probe verifies unchanged tracked runtime paths, V2
dataset digest and semantic catalog identity before execution. Diagnostic cases
are exploratory; none are blinded held-out validation.

## Reproduction and boundaries

From `backend/`, supply `DATABASE_URL` pointing to the unused application database
on the isolated cluster, `POSTGRES_TEST_DATABASE_URL` pointing to
`127.0.0.1:55447/queryops_w6a_composition_test`, and
`POSTGRES_TEST_DATABASE_DISPOSABLE=1`. The normal disposable-database guard checks
that these identities differ. Credentials belong in the operator environment.

```bash
PYTHONPATH=. .venv/bin/python ../docs/audits/w6a/composition_probe.py \
  --initialize --out ../docs/audits/w6a/composition-results.json
```

`--initialize` is only for an empty disposable database: migrate to head, then seed
medium/42 at `2026-11-01T09:20:36+00:00`, without reset. Omit it for a rerun.
The probe asserts the assigned endpoint and database name. It applies the normal
request authorization, QueryEngineService validation, deterministic renderer, SQL
safety validator, conformance, resource authorization and RLS runtime. The unchanged
baseline, semantic scorer, provenance extractor and result scorer judge the results.
This direct evaluator composition avoids pretending the synthetic fixture is a
real configured provider; no provider identity guard is weakened.

Every actual/baseline pair uses the same UTC, read-only, repeatable-read PostgreSQL
runtime transaction. Evidence records real transaction time, snapshot equality,
runtime role `queryops_query_runtime`, PostgreSQL 16.14, migration head, seed
fingerprint and table counts. The server clock is unchanged. Time-relative results
are paired within that snapshot; the fixed seed reference is not SQL `NOW()`.
The database receives seed and normal QueryRun writes only; result records remain
in memory. Tracked artifacts contain counts, hashes and bounded stage/shape metadata.

## Failure matrix

All medium009 rows below compare with the unchanged 16-device baseline under the
seeded analyst's assigned scope. Successful pairs are complete/exhausted; neither
the 100-row safety bound nor RLS explains these differences.

| Fixture | Actual / expected | First finding | Attribution |
| --- | --- | --- | --- |
| Intended posture OR plus outdated software, DISTINCT | 16 / 16 | Correct; all stages pass | Existing OR algebra and runtime support this answer |
| Compliance status only plus outdated software | 11 / 16 | `required_rule_missing`; runtime stages pass | Legal plan omits the broader business definition |
| Posture rule omitted entirely | 48 / 16 | `required_rule_missing` | Missing intent can broaden the answer too |
| Selected OR plus explicit status branch | 11 / 16 | Row mismatch; semantic contract reports rules correct | Selected-definition conformance is weaker than business-intent coverage |
| Selected OR plus antivirus branch | 9 / 16 | Row mismatch; semantic contract passes | Same extra-conjunct mechanism |
| Selected OR plus disabled-encryption branch | 4 / 16 | Row mismatch; semantic contract passes | Same extra-conjunct mechanism |
| Selected OR plus all three explicit branches | No actual execution | `composition_rule_overconstraint` at plan validation | Existing full-collapse protection works |
| All three branches without selecting OR | 1 / 16 | `required_rule_missing`; runtime stages pass | Validator checks the selected plan, not an independent English oracle |
| Intended OR, no DISTINCT | 25 rows / 16 devices | Row mismatch; semantic contract passes | Detail DISTINCT intent gap; duplicate installs multiply devices |
| Service-account definition | 11 / 11 | Correct | Simple catalog predicate control |
| Terminated employee with active account | 4 / 4 | Correct | Composite catalog dependency control |
| Terminated employee only | 4 / 4 | `required_concept_missing`, comparison incorrect | Equal counts and equal current records do not prove intent correctness |
| hard005 canonical device/user outputs | 1 / 1 | Duplicate output labels; comparison unestablished | Deterministic delivery loss described below |
| hard005 narrowed to active human inactive accounts | 0 / 1 | Row mismatch | Extra catalog narrowing remains legal but changes business answer |
| hard005 user output replaced by selected FK | 1 / 1 | `required_output_missing`, `result_grain_mismatch` | Unique labels alone do not satisfy the unchanged contract |
| hard005 device output replaced by selected FK | 1 / 1 | `result_grain_mismatch` | Same contract limitation, distinct from duplicate-label loss |
| Exploratory inactive-directory-user definition | 26 / 26 | Correct | Current temporal predicate matches the independent same-snapshot SQL |
| Same exploratory question, extra active-human narrowing | 9 / 26 | Row mismatch; semantic contract passes | General composition issue beyond device posture |

The two FK variants are row-comparison correct **before** the semantic-contract
veto; the authoritative combined result remains incorrect. No baseline or expected
answer is changed. The current direct-detail grain check uses required literal
fields; this is counter-evidence against treating FK substitution as a complete
workaround.

The business-term file, semantic catalog composition rule, deterministic template
and medium009 V2 baseline all agree on posture:
compliance status OR missing/outdated antivirus OR disabled encryption. The narrower
`non_compliant_device` concept intentionally describes compliance status alone.
Both definitions are available to the planner. Their distinction explains a
plausible legal-plan failure, but offline fixtures cannot establish why a model
would choose one.

The October audit's historical 11-versus-16 observation remains dated evidence.
The current fixture happens to reproduce those counts on the current deterministic
seed; it is **not** a replay or reproduction of the historical model selection.
No raw historical provider payload was used to construct a model-quality claim.

## Confirmed deterministic duplicate-label defect

The unchanged hard005 contract requires both `devices.id` and `directory_users.id`.
The canonical supplied plan validates, renders, passes safety/conformance and
executes. The renderer emits the two fields without aliases, producing SQL column
labels `["id", "id"]`. The SQL executor then converts a mapping to `dict(row)`,
leaving a single key in the delivered record. A diagnostic replay of that already
validated SQL on the same authorized read-only snapshot confirms the values at
the duplicate-label positions differ. The report stores only that boolean and
column/key counts. The baseline has `["device_id", "user_id"]` and two mapped keys.

This is a user-visible value-loss defect with high confidence, not solely an
evaluator inconvenience. The provenance extractor additionally rejects
`output_name_duplicated`, so result correctness becomes unestablished. Plan field
references have no alias property. Adding output fields does not remove the
collision between the two required canonical IDs; grouping/aggregation does not
provide an alias for the original detail field. The two bounded FK alternatives
remove the label collision but fail the current semantic contract as recorded
above. This is not an exhaustive enumeration of all plans; the direct canonical
case already proves the defect.

Relevant unchanged sources:

- [Output field schema and validation](../../../backend/app/query_engine/semantic_plan.py)
- [Renderer SELECT items](../../../backend/app/query_engine/sql_renderer.py)
- [Runtime mapping conversion](../../../backend/app/query_engine/sql_executor.py)
- [Provenance duplicate-name rejection](../../../backend/app/evaluation/provenance.py)
- [Detail grain and selected-rule scorer](../../../backend/app/evaluation/scoring.py)
- [Business terms](../../../backend/app/domains/it_operations/domain_pack/business_terms.yaml)
- [Semantic catalog](../../../backend/app/domains/it_operations/domain_pack/semantic_catalog.yaml)
- [V2 contracts](../../../backend/app/domains/it_operations/domain_pack/evaluation_questions_v2.yaml)

## Confidence, counter-evidence and smallest next scope

High confidence: intended OR rendering is already supported; legal plans can miss
or over-narrow business intent; duplicate labels lose one distinct required value;
the existing evaluator catches the demonstrated wrong medium009 results. The
semantic-contract score alone misses missing DISTINCT and extra single-branch
narrowing, while full result comparison catches them on this data. That does not
justify turning lexical matches into binding production intent.

The exploratory inactive control contains **zero null-login rows** in the assigned
analyst scope and 26 older-login rows. It therefore verifies the time branch but
does not positively exercise a null record. Catalog/SQL inspection supports the
null branch; a future isolated fixture with a null value is still required. No
fixture writes were added just to improve coverage. The successful simple and
composite controls argue against a blanket catalog/rendering failure.

The smallest justified first W6b correction is deterministic output identity:
preserve all requested values when field labels collide, with stable renderer-owned
aliases and aligned provenance/consumer behavior, retaining unique-name behavior.
This can preserve the provider plan schema. Acceptance should include canonical
hard005 on PostgreSQL, two unequal colliding ID values surviving delivery, distinct
column keys, successful unchanged result comparison, and regression checks for
single-table fields, grouped outputs, joins, dashboard/export identity and row
limits. Preserve fail-closed output/grain checks; do not loosen the frozen answers.

The model's propensity to omit posture OR or DISTINCT remains unmeasured on the
current configuration. These diagnostics do not justify a prompt correction or
model replacement yet. The consolidated [Hebrew report](../2026-11-01-w6a-semantic-diagnosis-he.md) owns the final proposed budget. The narrower six-call alternative below is component research only, not an additional authorized sequence. A separately approved follow-up could use configured
`gpt-5.6-terra`, low reasoning, 2048 output tokens, 45 seconds, retries 2, with
medium009 plus five predeclared composition contrasts, once each: at most six
logical calls and eighteen billable HTTP attempts if every request exhausts two
retries. Freeze exact questions before approval. Its value would be distinguishing
selection/over-narrowing frequency from already-supported downstream execution;
it would be diagnostic only, not qualifying canary or held-out evidence. An
independently authored unseen held-out set belongs in W6b/W6c verification, after
the correction scope is approved, and must not be used for tuning.

No production changes, provider calls, release qualification, broad suite or browser
QA were performed. These results do not establish live model reliability or null
record coverage; the proposed correction and any live budget still need approval.
