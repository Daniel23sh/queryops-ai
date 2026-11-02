# W6c proposed live diagnostic — NOT AUTHORIZED OR EXECUTED

This is a separate operator decision, not a release canary or Full40. Offline
manual witnesses cannot establish English interpretation, refusal/clarification
selection, the impact of optional definitions, model latency or provider cost.
The questions below are now exposed diagnostic cases, not a future blind test.
Keep their original oracles; do not tune or rerun after seeing failures.

## Exact proposed configuration and budget

- API model label: **`gpt-5.6-terra`**, the repository's configured project model.
  Actual account/model availability has not been checked. Failure of availability
  is a stop, not permission to substitute a model.
- Current production system instructions and strict SemanticPlan response schema,
  official `https://api.openai.com/v1`, Responses API, `store=false`, reasoning
  `low`, `max_output_tokens=2048`, timeout **45 seconds**, SDK `max_retries=0`.
  Retry zero is proposed solely for this separately authorized diagnostic; no
  settings, prompt or model have been changed in the product by W6c offline.
- **12 logical calls maximum, one per question, 12 physical HTTP dispatches maximum**,
  no repair, fallback, manual retry, alternate prompt, model or question.
  First transport/auth/config/refusal/fatal failure stops the sequence. A valid
  structured clarification or unsafe outcome is recorded as an outcome, not retried.
- Before live execution, the diagnostic runner must verify a pre-dispatch hard
  cap of one HTTP dispatch per logical call and 12 for the entire experiment,
  including redirects. Redirects are not followed. The normal SDK retry setting
  alone is not proof of this physical-attempt bound. If that bounded diagnostic
  transport cannot be verified without product changes, do not run; return for
  a revised approval. It has not been implemented or exercised here.
- Freeze exact source, V2/catalog digests, synthetic database state and provider/
  runtime fingerprint with a fresh reference time (within 24 hours). Record exact
  installed dependency versions, reasoning/output/timeout/retry settings. Offline
  W6c's small-plus-contrast fixture is diagnostic only; it is not an eligible V2
  release environment. For diagnosis, use a fresh equivalent diagnostic fixture;
  compare each accepted plan and independent oracle on one read-only snapshot.
- Retain safe stage statuses, counts, measured call/dispatch/token/latency values
  and fingerprint only. No rows, SQL, response bodies, provider text, scope keys
  or secrets in the evidence PR. Unknown/partial usage stays null/incomplete.

At most 24,576 successful-response output-token allowance is configured across
12 calls. This is not a total token or money guarantee: inputs, reasoning,
failed/abandoned work and incomplete server usage can affect charged usage.
There is no estimated dollar claim or assumption that an error was free. Report
physical attempts separately from logical calls and stop on incomplete usage
before proceeding to the next question.

## Frozen questions and diagnostic value

Exact questions are the bytes under the following IDs in
[heldout-v1.json](heldout-v1.json), frozen at `e22831e` with raw SHA256
`ed5946c1f837b344563ef770b687e83ed1e6cce182a42820b9e2e7df9d4e8b8a`.
No paraphrase substitution or extra case is authorized by approving this list.

| Order | ID | Diagnostic value |
| --- | --- | --- |
| 1 | W6C-001 | Select NULL-or-old check-in semantics without adding posture/account filters |
| 2 | W6C-002 | Clarify an undefined business eligibility phrase |
| 3 | W6C-003 | Clarify unsupported firmware/CVE metadata |
| 4 | W6C-004 | Preserve not-locked population, including disabled/service accounts |
| 5 | W6C-006 | Choose full posture OR, conjunctively narrowed only by staleness |
| 6 | W6C-008 | Select unsupported/high-risk installs and DISTINCT endpoint grain |
| 7 | W6C-009 | COUNT DISTINCT endpoints rather than multiplying witness records |
| 8 | W6C-010 | Request both endpoint/install identities; backend output mapping is already verified |
| 9 | W6C-011 | Choose 90-day non-mandatory/non-exception definition rather than the 60-day alternative |
| 10 | W6C-012 | Avoid unused-license filters on an explicitly broad active-assignment request |
| 11 | W6C-013 | Do not infer privilege from the recency concept's misleading ID |
| 12 | W6C-020 | Preserve explicitly requested encryption-off narrowing of the OR |

W6C-007 is excluded: its preserved-two-optional-branches witness has an offline
encoding limitation. A live model cannot make an unavailable plan encoding legal.
W6C-014's new packing stress passed availability; the already exposed CA-B01
miss remains known. Neither is used to change retrieval or choose these questions
after measuring provider output; no provider output exists for them.

## Stop conditions and decisions

Before the first billable request require explicit approval of the exact model,
all settings, ordered 12 IDs, logical/physical caps, no-retry policy, verified
hard dispatch guard and the source/config/database identities. A different model,
budget, question, prompt, fixture semantics or fallback requires a new decision.
Stop before dispatch if authorization/context/projection exceeds existing bounds,
identity differs, DB is not disposable, guards are unavailable, or frozen bytes
change. Stop after any renderer/conformance/security failure, unexpected metadata
disclosure, transport failure, incomplete usage, redirect or reached budget.
Keep semantic selection mistakes as diagnostic observations; do not fix and rerun.

Separately decide how V1 should handle W6C-007's unsupported population-preserving
optional OR: an explicitly bounded future implementation proposal, or an explicit
unsupported/clarification product boundary. Offline W6c does not authorize either
product change. The known P3 packing risk remains accepted and unmodified.

This diagnostic does not satisfy the fixed three-canary/full40 sequence,
thresholds, manual QA or V1 release qualification in
[the release policy](../../evaluation/v1-quality-gates.md).
