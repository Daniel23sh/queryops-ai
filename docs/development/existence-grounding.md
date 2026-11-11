# Existence versus aggregate output guidance

The W6c correction distinguishes a positive-existence condition from a request
for aggregate output. For example, “List user IDs with at least one failed login”
does not request a count column. The same distinction applies to related software
installations and other catalog relationships; it is not keyed to W6c cases.

The numeric-threshold fallback in `semantic_grounding.py` abstains from suggesting
COUNT, GROUP BY or HAVING for `>= 1` / `> 0` when the existing recognizers find no
explicit count or grouping request. The related-detail fallback also abstains in
that situation, so suppressing the count does not instead suggest a child-record
identity or `distinct=false`. Explicit authorized field hints remain available.

Explicit count/group requests, thresholds such as `> 5`, `>= 2`, `= 1` and `<= 1`,
and canonical metric handling retain their existing behavior. This is a bounded
abstention rule using the existing recognizers, not a complete natural-language
parser. Unrecognized or implicit result shapes remain the provider's decision.

The [semantic ownership contract](semantic-ownership-migration.md#pr57-production-boundary)
is unchanged: ordinary wording supplies Suggested Intent only; Required Intent
remains unset. The correction does not force DISTINCT, rewrite provider-selected
fields, reject legal alternative plans, select business definitions, or change
SemanticPlan, validation, rendering, provider instructions, catalog, authorization,
SQL safety, runtime roles or PostgreSQL RLS. Candidate authorization, dependency
closure and the 16,000-byte projection limit remain authoritative.

## Evidence and limits

The current deterministic projection of frozen W6C-008 reproduced its recorded
live-input projection hash and suggested an unsolicited count/group/HAVING shape.
Independent review also reproduced this behavior for user/login questions.
Removing this misleading guidance is independently justified. The actual provider
output identities from W6C-008 were not retained, so this is not a demonstrated
cause or a demonstrated live fix for that historical output-contract failure.

W6C-012 returned clarification without a plan. Its reason was not retained; no
backend defect explaining that response was established. Active assignments still
require only their selected active-status definition. Available unused,
high-confidence, mandatory and exception definitions do not become hidden filters.
The original [frozen questions](../audits/w6c/heldout-v1.json), witnesses, fixtures,
historical results and terminal journals remain unchanged.

## Regression boundary

Deterministic contrasts cover numeric/word existence thresholds in device/software
and user/login domains, count/group and nonexistential controls, detail-fallback
abstention, authorized field hints and optional license definitions. PostgreSQL API
tests use a controlled provider to contrast unique parent IDs with intentional
child-detail fanout, assigned scope versus affiliation, hidden witnesses and
clarification without execution. These supplied plans establish runtime behavior,
not provider interpretation accuracy.

Existing candidate-authorization and reverse-LEFT tests, plus the six frozen W6c
witnesses through fake HTTP/SDK parsing, retain scope/RLS, OR and independent-WHERE
coverage. Run focused checks with:

```bash
cd backend
.venv/bin/pytest tests/test_existence_grounding.py tests/test_semantic_grounding.py tests/test_candidate_availability.py tests/test_openai_provider.py tests/test_query_engine_service.py -q
.venv/bin/pytest tests/test_existence_grounding_postgres.py tests/test_candidate_availability_postgres.py tests/test_reverse_left_postgres.py tests/test_w6c_v3_postgres.py -q -rs
```

The second command requires a new explicitly disposable PostgreSQL environment;
relevant skips are missing evidence. PR #76 merged this correction; future changes
follow the [validation model](validation-model.md). This correction
invalidates earlier candidate identities; diagnostic successes never replace the
separately authorized matching V2 canary/full40 and manual QA required by
[the release policy](../evaluation/v1-quality-gates.md).
