# W6c live diagnostic v2 — preparation only, no execution approval

This successor is separate from the unchanged [original proposal](live-experiment-proposal.md)
and [offline evidence](../2026-11-02-w6c-offline-validation-he.md). The machine
contract is [live-v2.json](live-v2.json). No real OpenAI request, model-list request,
paid evaluation or live interpretation has been performed or authorized here.

## Configuration and selection

Exact model `gpt-6.1-terra`; Responses API at `https://api.openai.com/v1`, current
unchanged product system instructions and strict structured SemanticPlan output,
`store=false`, reasoning `low`, output cap 2048, timeout 45 seconds, retries 0.
Official [model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
confirms the model ID, Responses, Structured Outputs and low reasoning. Account
access, actual returned model identity and natural-language interpretation remain
unproven. Any mismatch or unavailability stops; no substitution is permitted.
Normal product retry policy remains 2. Environment values control normal product
configuration; the diagnostic requires every live setting explicitly to match
this versioned configuration. It never silently applies diagnostic restrictions
to ordinary requests. See [migration inventory](../../development/terra-configuration-migration.md).

The ordered IDs are:

| Position | Case | Purpose |
| --- | --- | --- |
| 1 | W6C-001 | NULL-or-old staleness without gratuitous posture/account narrowing |
| 2 | W6C-002 | Structured clarification for undefined eligibility |
| 3 | W6C-003 | Structured clarification for unavailable firmware/CVE metadata |
| 4 | W6C-004 | Not-locked population, including disabled/service accounts |
| 5 | W6C-006 | Complete posture OR with only the independent staleness restriction |
| 6 | W6C-008 | Unsupported/high-risk installs at DISTINCT endpoint grain |
| 7 | W6C-009 | COUNT DISTINCT endpoints under witness fanout |
| 8 | W6C-007 | Select left_reverse and retain both optional OR branches |
| 9 | W6C-011 | 90-day non-mandatory/non-exception definition |
| 10 | W6C-012 | Broad active assignments without unused-license restrictions |
| 11 | W6C-013 | Recency concept does not imply privilege |
| 12 | W6C-020 | Explicit encryption-off restriction remains independent of posture OR |

W6C-010 already has deterministic output-identity/backend coverage. W6C-007 now
has the bounded encoding introduced by merged PR #70, but choosing that encoding
from English still needs live validation. It replaces W6C-010 at position 8;
the other IDs and all original question bytes/oracles remain unchanged. This is
an exposed diagnostic set, not a new blind generalization test. Selection was
frozen without provider outcomes. Do not tune the prompt, catalog, questions,
oracle, fixture semantics or model based on diagnostic results; do not fix/rerun.

The raw heldout file hash remains
`ed5946c1f837b344563ef770b687e83ed1e6cce182a42820b9e2e7df9d4e8b8a`.
The contract records each question's exact UTF-8 SHA256 in order, original
proposal/freeze hashes, model settings, caps and acceptance criteria. The original
W6c freeze, fixtures, manual witnesses, results, proposal and review are read-only.
V2 dataset digest remains `6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f`;
catalog digest remains `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`.

## Hard boundary and non-resumable budget

`backend/scripts/w6c_dispatch.py` wraps the actual synchronous HTTP transport.
At most 12 logical calls, 12 physical dispatches and one dispatch per question
are allowed. Only the exact preflight-approved POST body to `/v1/responses` can
cross it. Model, instructions, schema, prompt, reasoning, output cap and store
policy are included in that body identity. There are no tools, repair/fallback
calls, SDK retries, HTTP transport retries or followed redirects. Credentials
and official endpoint are explicit; ambient proxies are ignored.

Before the underlying transport is touched, a dispatch reservation is written
and fsynced to a mode-0600 journal, and the containing directory is fsynced.
The fixed per-OS-account location is
`~/.local/state/queryops/w6c-live-v2/dispatch.jsonl`; the path comes from the OS
account record, not the caller's `HOME`. It is shared across checkouts and source
revisions and has no CLI override. Exclusive creation rejects concurrent starts
and all restarts, including a crash before the first physical send. There is no
resume/reset command. Do not delete, relocate or truncate it. A new experiment
version after any partial/completed run requires a separate reviewed change and
explicit operator approval; a new checkout or manifest is not a fresh budget.
This is a trusted local-operator boundary, not protection from an OS administrator
who can delete state or run arbitrary HTTP clients outside the diagnostic.

Any transport/authentication/HTTP/redirect/stream failure, refusal, malformed
structured output, fatal error, partial/unknown/inconsistent usage, security,
rendering, SQL safety or conformance failure stops before the next question.
Structured clarification/unsafe outcomes and safe semantic mismatches are recorded
without retry. Wrong semantics do not authorize tuning or extra calls.

Logical events, pre-dispatch physical reservations, latency, bounded usage fields
and terminal failures are recorded separately. Each completed case's safe outcome
and semantic/oracle booleans are fsynced before the next question; a later fatal
failure cannot erase earlier non-repeatable observations. Failed/abandoned work is not assumed
free. Missing usage remains null/incomplete; partial known counters are preserved,
not turned into zero or a complete total. A reservation left without a result is
an attempted dispatch with unknown usage, never permission to resend. The 24,576
successful-response output allowance is not a total-token or monetary guarantee.

## No-external-network preparation

From a clean committed checkout, use a **new disposable PostgreSQL 16 cluster**
and an empty database named exactly `queryops_w6c_v2_test`. Existing application
databases are forbidden. The initializer refuses a nonempty DB and never resets
one. A new DB inside a cluster with existing action-runtime roles can fail the
existing migration's role-collision protection; do not remove those roles to make
it pass. Use a separate disposable cluster. No-network means no external/provider
network: local PostgreSQL connections are required.

For example, export the synthetic disposable URL and guard flag, with
`DATABASE_URL` referring to a different application database, then from `backend/`:

```sh
.venv/bin/python -m scripts.w6c_live --initialize \
  --reference-time 2026-11-03T12:00:00+00:00 --out /tmp/w6c-preflight.json
.venv/bin/python -m scripts.w6c_live --manifest /tmp/w6c-preflight.json \
  --dry-run --out /tmp/w6c-dry-run.json
```

Replace the example time with the actual fresh UTC reference (maximum age 24h,
maximum future skew 5m). Preparation does not need an API key and never constructs
a network HTTP transport. Dry run uses the real SDK parser with `MockTransport`
and hand-supplied frozen witnesses; its synthetic token counts are not provider
measurements or cost evidence. `--help` and preparation are safe defaults; an API
key or `LLM_PROVIDER=openai` alone cannot enable diagnostic live execution.

Before DB construction/import of frozen executable artifacts, verify clean source,
raw frozen files, ordered question hashes, unchanged V2/catalog identities and
versioned configuration. The v2-only fixture adapter reuses frozen contrasts with
the approved fresh reference and deterministic omitted timestamps. It does not
edit historical fixture bytes. The seeded reference must match the actual DB.

Preflight binds exact source, config/request/schema/projection hashes, all installed
provider/runtime versions, dependency-manifest hash, migration, PostgreSQL version,
full synthetic data fingerprint, role/grant/RLS-policy fingerprint and fresh time.
It validates request authorization, candidate closure/context bounds and identity
exclusion using production projection/validation. Ten manual positive witnesses
must match their independent read-only RLS SQL oracles; the other two cases expect
clarification. Each actual/expected comparison uses one repeatable-read snapshot
under `queryops_query_runtime`, read-only and UTC, with complete delivery.

Compare full population/output shape (including limit, grouping and HAVING), field
identities and aggregate function/target/DISTINCT semantics; aggregate aliases are
not meaning. An unrequested top-N cannot pass merely because a fixture is small.
For W6C-007 additionally record both `left_reverse` selections, membership-group
`left`, the OR composition rule, the independent on-leave restriction and actual
inclusion of both group-only and event-only synthetic populations. Do not claim
general semantic equivalence from matching fixture rows alone.

Before each physical dispatch, recheck clean source, reference freshness, runtime
settings/credentials, full data and security-policy identities, current effective
permissions/scopes and exact authorized request body. Re-run full preflight before
constructing the live client. Local artifacts contain only safe hashes, versions,
counts and statuses: no API key, URL credentials, raw provider bodies, SQL, rows,
user identities or sensitive scope identifiers. Never commit raw manifests,
journals or run outputs. Publish only reviewed safe summaries.

## Approvals still required before Live

1. Merge the reviewed preparation candidate separately. Fetch main and regenerate
   the source/configuration/runtime/data fingerprint against that **eventual merged
   SHA** and a new fresh disposable fixture. This PR's SHA is preparation evidence,
   not a finalized merged-candidate live fingerprint.
2. Review passing final-head CI, adversarial guard tests, preflight/dry-run and
   fresh-context correctness/security review. Preserve fixed V2 release gates.
3. Obtain explicit human operator approval for the exact fingerprint, merged SHA,
   `gpt-6.1-terra`, low/2048/45/0, ordered IDs/hashes, fixture identity, 12 logical
   calls/12 physical dispatches/one per question, no retry/resume/substitution and
   all stop conditions. This task grants none of that billable authority.
4. Only after that approval, place a separate local JSON outside the repository
   with exactly `schema=queryops-w6c-operator-approval-v2`, `approved=true`,
   `fingerprint`, `source_git_sha`, `model`, `max_logical_calls=12`,
   `max_physical_dispatches=12`, `max_dispatches_per_question=1`,
   `no_retry_no_resume=true`. The operator sets the explicit live environment
   including `OPENAI_MAX_RETRIES=0` for this invocation only and supplies both
   `--live --approval <local-file>` and the matching `--manifest`.

The CLI also requires HEAD, local main and origin/main to name the approved
merged revision. Changing source, settings, questions, fixture, model, budget,
prompt or fallback requires a new decision. This diagnostic does not satisfy
the fixed V2 three-canary/full40 qualification, thresholds, manual QA or release
readiness in [the quality gates](../../evaluation/v1-quality-gates.md).
