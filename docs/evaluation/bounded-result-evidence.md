# Bounded-result evaluation evidence

Policy: `queryops-bounded-result-evidence-v1`

QueryOps evaluates a bounded production delivery separately from the semantic
answer population. The production query still uses its normal SQL validator,
default 100-row safety bound, existing explicit-limit ceiling, provider-call
count, authorization and RLS. Evaluation may collect auxiliary rows only to
establish a comparison; those rows never replace the delivered result or appear
in product read models.

## Outcomes

`comparison_state` is persisted in safe evaluation metrics as one of:

- `correct`: complete comparable evidence matches under the existing value,
  stable-key, multiplicity, grain, measure, tolerance and ranking rules, and the
  delivered rows are a valid bounded delivery.
- `incorrect`: compatible evidence proves a membership, multiplicity, value,
  output, order or other semantic contradiction.
- `unestablished`: available evidence proves neither correctness nor
  incorrectness. `result_correct` is null, the case fails, receives no result
  credit, remains in every applicable denominator, and cannot satisfy readiness
  or stability.
- `not_reached`: the original case failed before result comparison.
- `not_applicable`: result comparison does not apply to the expected outcome.

`EvaluationResult.status` remains the compatible pass/non-pass projection:
`succeeded` for a passing case and `failed` otherwise. No database migration is
needed. Historical records remain unchanged and readable, but records without the
current comparison-evidence contract cannot qualify a new candidate.

## Bounds and permitted transformation

Every V2 answer contract declares a structural answer bound: `population`,
`limit`, or `top_n`. This is evaluator-owned reviewed semantics; no English parser
or baseline presentation is used. Production SQL validation records whether its
outer bound was input SQL, safety-added, or safety-clamped, plus the original and
effective limit.

Auxiliary evidence may widen only the single outer bound whose safety origin is
recorded by validation. An intact input-origin bound is never removed. A
safety-clamped bound may be restored only up to its separately recorded original
value and the evidence cap; this preserves a semantic or planner bound rather
than treating it as an evaluator limit. Unknown-origin and nested limits remain
ineligible. Selected expressions, predicates, joins, `DISTINCT`, multiplicity,
grouping, `HAVING`, aggregates and ordering are unchanged. The transformed
statement passes the normal validation, resource authorization and query-runtime
execution path. It never repairs a plan, masks conformance or execution failure,
or turns an invalid delivered result into a valid one.

## Resource and execution contract

At most one auxiliary answer `SELECT` per side and two per case run in one
evaluator-scoped, read-only `REPEATABLE READ` transaction shared with the actual
and baseline executions. It opens after provider planning. All statements use the
same non-owner `queryops_query_runtime` role, exact `UserAccessContext`, assigned
scopes, transaction-local RLS, UTC timezone, transaction time and a resource
metadata snapshot captured in that transaction before the runtime role is set.
Persistence is outside this transaction.

The versioned budget is:

- 1,000 retained evidence rows per side and a SQL lookahead of 1,001;
- five seconds per auxiliary statement and ten seconds total wall time;
- 8 MiB of normalized comparison payload across both sides;
- no retries, limit escalation, provider fallback or extra provider call.

Exactly 1,000 rows followed by exhaustion is complete. A 1,001st row proves row
budget exhaustion. Payload and row acquisition stop at their limits, and the SQL
statement timeout still bounds internal database work. A monotonic acquisition
deadline also bounds cumulative row fetching and normalization. Successful
qualification must remain within the per-statement and combined wall-time
budgets; truthful timeout or overrun observations remain valid persisted
non-qualifying evidence.
Unsupported volatile or external-state expressions are non-comparable even when
their first result is below the production cap. Context mismatch, unavailable
comparison proof, timeout, validation failure, execution failure or budget exhaustion yield safe
`unestablished` evidence unless an independent complete compatible witness already
proves a defect.

Completeness, per-side comparison eligibility, pair context compatibility and the
safe limitation reason are separate evidence fields. Replacing one limitation
reason cannot make structurally unsupported evidence eligible.

## Delivery completeness

`delivery_completeness` is independent from correctness:

- `complete`: exhaustion or an intact semantic bound proves the requested answer
  was fully delivered;
- `safety_limited`: a proven production safety bound may have cut the delivery;
- `unknown`: completeness cannot be established.

`correct` plus `safety_limited` is valid evaluation evidence but must always be
shown as partial delivery. A row count, `truncated=false`, an equal visible subset
or a passed semantic contract does not prove completeness. Product UI receives
only this delivery state and never auxiliary rows or an invented exact total.

The legacy `missing_row_count` and `extra_row_count` metrics remain returned-count
deltas for compatibility. Read models also expose
`returned_row_count_shortfall` and `returned_row_count_surplus`; neither pair
claims to measure missing or extra population members.

Run and breakdown summaries expose all five `comparison_state` counts. Their sum
equals the completed visible cases. `unestablished_count` remains the compatible
alias for the corresponding state count, while `failed_count` remains every
completed case whose top-level pass projection is false; it is not an
incorrectness count. Readiness and scoped read models recompute these aggregates
from validated visible case records rather than trusting stored summary totals.

## Proof boundaries

Complete unordered results compare as duplicate-sensitive multisets unless the
answer is `DISTINCT`. Grouped and aggregate results retain the established grain,
measure and numeric-tolerance rules. Semantic top-N keeps its requested bound and
ordering. Identical valid top-N answers can establish correctness without
exhausting the population beyond N. Ranking comparison accepts exact cutoff ties
without inventing an unrequested tie-breaker; differing unresolved cutoff tie
membership remains `unestablished`. An
unordered semantic `LIMIT` defines a bounded selection, not a particular set of
rows. Different or matching arbitrary selections remain `unestablished` unless
exhaustion or another complete compatible witness proves equality or a defect.

Planner-selected limits remain part of the answer SQL. Reaching an intact input
limit does not prove population completeness. Returning fewer rows than that
limit, without truncation and with a supported comparison shape, proves exhaustion
of that SQL answer. This does not override a failed semantic bound contract or
make nested/offset/volatile queries comparable. Different visible
partial subsets do not prove different populations, and identical visible subsets
do not prove equal populations. Baseline ordering is evidence only when reviewed
answer semantics require it; it is never copied into production planning.

An original validation, conformance, timeout or execution failure wins at its
original stage and prevents auxiliary execution. QueryRun persistence, execution
context teardown, baseline or auxiliary failure cannot overwrite the successful
production observation. Original delivered rows
remain an independent incorrectness witness when auxiliary acquisition fails.
Baseline validation, authorization, timeout and execution limitations retain
distinct safe reasons and execution counts. Metrics store only
versioned policy/budget identity, safe states, row counts, execution counts and
durations, and safe limitation reasons. They store no rows, SQL, provider content,
membership witnesses, scope keys or secrets.

The evaluator-only correction does not resolve the separate aggregate-grouping provider/runtime
contract (`itops-hard-004`), provider semantic reliability/composition
interpretation (`itops-medium-009`), other tracked DISTINCT enforcement gaps, or
unbounded pagination or full-population export.

## M10 W0 integration review

The 2026-10-28 review selected retention with narrow corrections, rather than a
rewrite or discarding the evidence model. The implementation addresses a real
ambiguity: equal limited prefixes do not prove equal answer populations. Treating
every bounded result as unknown would be smaller but would lose useful valid
measurements; removing caps or accepting prefixes would break correctness.

Pre-integration corrections restrict cached authorization metadata to table
resources, recognize supported input-limit exhaustion and identical valid top-N
answers, admit the legitimate three-canary incomplete UI state, and reject
malformed persisted string states/digests without raising. They do not change
provider prompts, historical baselines, safety/evidence budgets, RLS or thresholds.
The redundant unconditional top-N-boundary veto was removed; no replacement
abstraction was introduced. Actual integration and validation records belong in
[development history](../history/development-history.md) and current status in
[PROJECT_PLAN](../../PROJECT_PLAN.md).

At that W0 checkpoint, remaining work included exact-scope dashboards, atomic role
requests, scoped Evaluation reads and derived delivery disclosure. Actual package
completion and merge status belong in PROJECT_PLAN.md. Provider identity, usage
and independently validated semantic reliability remain separate packages, not
claims that the bounded-result baseline qualifies V1. The 8 MiB budget bounds
normalized retained comparison payload, not total Python process RAM; the ten
second budget bounds cumulative auxiliary acquisition, not provider planning plus
all observed executions.

## Product delivery through saved Cards and CSV

Product delivery completeness describes the rows delivered for the validated SQL
answer. It does **not** certify that the SQL correctly interprets the natural
language question, nor that an intact SQL top-N exhausts the underlying population.
The evaluator still uses its independently reviewed answer bound, semantic checks
and comparison evidence; product delivery states do not replace those proofs or
change readiness thresholds.

An intact input `LIMIT N` can be completely delivered as that bounded SQL answer.
If the execution row cap cuts it first, delivery is `safety_limited`; payload or
deadline exhaustion remains `unknown`. A safety-added/clamped limit reached by
the result remains `safety_limited`, even when `truncated=false` or the true
population happens to equal the returned count. No exact population total is
inferred. Below a known safety bound, successful unrestricted acquisition can
establish complete delivery.

Saving a Card links its SavedQuery to the existing server-owned QueryRun.
Re-execution revalidates the saved SQL under the current viewer and restores only
consistent server-persisted `validation.limit_source`, `input_limit` and
`effective_limit` fields matching the freshly validated outer limit. SQL is never
rewritten or widened for product refresh/export. A new refresh QueryRun retains
this allowlisted provenance and its fresh execution delivery state. Legacy,
missing or inconsistent provenance stays `unknown`; it is not relabeled as an
input/business limit merely because saved SQL now contains `LIMIT`. No migration,
raw result-row persistence or evaluator auxiliary evidence is added.

Card refresh exposes `delivery_completeness` and safe warnings. Visual clipping
is separate: tables initially show ten returned rows, disclose the displayed and
returned counts, and allow expansion to all already-delivered rows. Chart and
status previews disclose their actual visual subset. Expansion does not issue an
unbounded query or claim to recover rows omitted by database delivery limits.

Both CSV endpoints reauthorize and re-execute. CSV remains ordinary column/header
and data records, with no warning/comment rows mixed into the data. Responses add:

- `X-QueryOps-Delivery-Completeness`: `complete`, `safety_limited` or `unknown`.
- `X-QueryOps-Returned-Row-Count`: the actual exported row count, never a population
  total.
- Filename suffix `-partial.csv` or `-completeness-unknown.csv` when appropriate,
  including custom filenames within the existing safe length bound.

These headers and Content-Disposition are exposed through the existing CORS
policy. Download UI uses the **fresh export response**, including its returned
count, rather than assuming the Card's earlier state still applies. For example,
an intact SQL `LIMIT 500` can be partial in a 100-row Card refresh yet complete in
a permitted 500-row export. Missing or invalid response metadata is shown as
unknown. Audit records include only safe delivery state/counts, not result rows.
Current-viewer scopes, restricted-export policy, RLS, runtime role, SQL validation,
row caps and formula-injection sanitization remain authoritative.
