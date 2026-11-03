# W6c diagnostic observability after the first Live attempt

This is an additive offline instrumentation contract. The previously approved
[v2 experiment](../audits/w6c/live-experiment-v2.md), frozen inputs, question
selection, model/settings and acceptance criteria remain unchanged. The original
single-use journal remains terminal. This instrumentation cannot authorize or
resume that experiment; no new state location or experiment version is added.

## Independent comparison measurements

For a validated, safely executed plan and independent oracle on the same
repeatable-read/read-only RLS snapshot:

| Field | Meaning |
| --- | --- |
| `output_contract_match` | Boolean comparison of field identities, aggregate function/target/DISTINCT, row DISTINCT, metric, grouping, HAVING and LIMIT against the independent witness contract |
| `result_multiset_match` | `true`/`false` only when field/aggregate identities align uniquely; `not_evaluated` when output identities are incompatible or ambiguous |
| `oracle_equal` | Legacy conjunction: contract matches AND multiset matches; preserves its old acceptance meaning |
| `oracle_complete`, `same_read_only_snapshot` | Existing bounded-delivery/runtime guarantees, unchanged |

No model-selected aggregate alias is treated as semantic meaning. Oracle SELECT
order and normalized renderer order are aligned by semantic identities. Rows
remain an unordered multiset, including duplicates and NULL values; identities
are never inferred from coincidentally equal values. Different aggregate targets
or incompatible fields cannot yield a trustworthy result comparison. An
unrequested LIMIT can have contract=false while matching a small fixture's rows;
an extra restriction can have contract=true while changing its rows.

No raw rows, SQL, provider plans or output strings are persisted. The safe case
allowlist permits only booleans for existing/new contract fields and exactly
`not_evaluated` for the new multiset field. Unknown strings/fields/types fail
closed. Completed observations are still fsynced before the next logical call.
Legacy records without the new measurements remain readable; a legacy false
does not establish either independent measurement. Do not fill missing fields
from historical combined results.

## Transport measurements

`transport_failure_category` is additive; legacy `failure` codes remain intact.
The boundary records only these categories, not exception text or class names:

- `timeout`: HTTPX timeout family, including connect/read/write/pool/stream reads.
- `connection_failure`: HTTPX network or proxy failure.
- `protocol_failure`: HTTPX protocol/unsupported-protocol failure.
- `http_failure`: known non-success HTTP response.
- `redirect`: a redirect response; it is never followed.
- `unknown_interruption`: an exception/interruption outside those known types.
- `null`: success or a known diagnostic failure unrelated to transport, such as
  invalid response shape or missing/inconsistent usage.

A non-JSON HTTP error/redirect retains its known status category without keeping
the body. A malformed successful response remains a fatal `response_invalid`.
Complete/partial bounded usage is retained when available; absent telemetry
remains null/incomplete. All failures remain terminal, including unknown ones.
Old `transport_or_interruption` evidence has no recoverable specific category.

The actual transport reservation, O_EXCL journal creation, fsync ordering,
12/12/1 limits, one-dispatch-per-question, request-body/credential checks,
per-dispatch authorization/data/runtime rechecks, no retries/redirects and
fail-closed behavior are unchanged. No production provider, Evaluation scorer,
renderer, authorization, RLS, prompt or model semantics are modified.

The [historical diagnosis](../audits/w6c/post-live-diagnosis-he.md) distinguishes
confirmed observations, hypotheses and unavailable evidence. A future billable
experiment requires a separate decision and approval; these diagnostics are not
release qualification.
