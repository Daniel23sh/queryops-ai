# W9 entry decisions and qualification handoff

Historical reference: W9 subsequently froze a candidate and stopped after its first
canary failed. The dated proposals below are preserved as written, not current
pending work.

Decision draft — 2026-11-09. **Not approved.** Current scope and authorization live
in [PROJECT_PLAN](../../PROJECT_PLAN.md). This document proposes decisions and an
operator sequence; it changes neither executable gates nor authorization.
Merging it does not accept either decision or authorize freeze/provider requests.

## Residual W6c risk — pending owner decision

The [recorded diagnostic](../history/development-history.md#2026-11-04--w6c-v3-live-diagnostic-and-bounded-correction-decision)
completed six measured responses with four semantic acceptances. W6C-008 failed
the output contract; result multiset was `not_evaluated`, and actual selected
output identities were not retained. W6C-012 returned clarification without a
plan; its cause is unknown. Neither failure is proven fixed. The
[existence-grounding correction](../development/existence-grounding.md) addresses
a reproducible deterministic defect without establishing historical causation.

Proposed owner statement, to be explicitly accepted or rejected with decision
date and evidence reference:

> I accept these two documented semantic limitations for entering W9 only. I do
> not classify either historical result as passing or fixed, waive any Evaluation
> V2 threshold/security/zero-defect gate, or authorize freeze or provider calls.
> Fresh matching qualification and complete manual QA remain required for V1.

This is compatible with investigation closure and W9 entry, not release approval.
No further product correction is established by the missing historical evidence;
do not reconstruct it, retune cases, or repeat W6c under this decision. Preserve
both terminal journals and all frozen artifacts.

## Live transport choice — pending owner decision

The production [settings](../../backend/app/query_engine/provider_config.py) and
[HTTP client](../../backend/app/query_engine/openai_provider.py) currently use
`gpt-6.1-terra`, Responses API strict structured `SemanticPlan`, reasoning `low`,
maximum output tokens `2048`, timeout `45s`, SDK retries `2`, `store=false`, and
official endpoint `https://api.openai.com/v1`. Redirects are enabled by the SDK's
default HTTP client. This is a proposed exact profile, not an approved execution.

| Choice | Qualification and operational implications |
| --- | --- |
| Retain production behavior (recommended) | Measures the supported profile without a new code boundary. Retries can recover transient failures but increase attempts, time and possible charges. There is no enforced aggregate physical-dispatch cap; operator gates limit run invocations, not in-flight retries. |
| Introduce a hard execution bound before freeze | Gives enforceable attempt control, but needs separate authorization, implementation, durable budget/terminal semantics and adversarial transport/security review. It may turn recoverable failures into terminal ones and changes the measured behavior. It must merge, pass CI and be frozen before any fresh qualifying manifest/evidence; a post-freeze change invalidates that identity. |

Retaining production behavior is the smallest defensible choice for this manual,
bounded run sequence, **if the owner accepts its attempt/cost exposure**. Do not
silently replace it with W6c's diagnostic guard, disable retries/redirects, or
describe telemetry as an execution cap. If a strict physical budget is mandatory,
the hard-bound implementation is a blocker before freeze; this documentation task
does not implement it. Record the owner's choice/date/reference before proceeding.

For the audited OpenAI SDK `2.46.0` / HTTPX `0.28.1`, two retries permit three SDK
tries per logical call; the client permits 20 redirects (21 dispatches per try).
The derived ceiling is 63 HTTP dispatches per call, not 63 billable responses.
Reverify this against the actual frozen runtime before live authorization.

| Stage | Cases | Maximum logical calls | Attempts with retries, without redirects | Derived maximum including redirects |
| --- | ---: | ---: | ---: | ---: |
| Three canaries | 30 | 27 | 81 | 1,701 |
| One conditional full40 | 40 | 31 | 93 | 1,953 |
| Total | 70 | 58 | 174 | 3,654 |

Templates and authorization-denied cases bypass the provider; unsafe/clarification
cases may call it. These are profile-derived bounds, not application budget
guards. The [64-per-call telemetry bound](v1-quality-gates.md#usage-and-retry-evidence)
does not stop dispatch. Unknown attempts/tokens remain unavailable, never zero.
Correctly represented incomplete usage need not disqualify quality evidence;
malformed/inconsistent evidence fails validation. Prices, retries, caching and
unobserved failure usage make charges uncertain. Re-estimate from official prices
and the prepared runtime before authorization; no run/attempt estimate is a
monetary cap. Any stricter stop-on-unknown-usage condition needs explicit agreement.

## Post-merge handoff

Follow the existing [release order](v1-quality-gates.md#final-release-order),
[identity contract](v1-quality-gates.md#environment-identity-and-invalidation) and
[W8 safeguards](../development/reproducible-validation.md), without changing policy:

1. **Resolve decisions and authorize offline preparation.** After this PR merges,
   record explicit residual-risk acceptance and transport choice, then obtain
   authorization for W9 Offline Freeze and Evaluation V2 Preparation. If a hard
   bound is chosen, complete its separately reviewed implementation first.
2. **Verify and freeze final main.** Fetch and require clean
   `HEAD = main = origin/main`; verify all six CI jobs on that exact resulting SHA.
   PR #76's `b2519b2909e5b5615f2211afd6c7e4aa74ae09ad` and passing
   [run 41907001375](https://github.com/Daniel23sh/queryops-ai/actions/runs/41907001375)
   are a historical checkpoint, not permission to skip post-reconciliation CI or
   use a feature-branch manifest. Freeze only in the later authorized task.
3. **Prepare an owned isolated PostgreSQL 16 V2 database.** Prove ownership and
   emptiness before migrations/reset; never adopt user resources. Record safe
   cluster/container/volume identity separately from the sanitized manifest. Run
   Alembic upgrade/current/check and verify runtime roles/grants/RLS/exact scopes.
   Use separate disposable resources for destructive integration checks. Then use
   the existing [seed CLI](../../backend/scripts/seed_it_operations.py) with
   `--profile medium --reset --reference-time <fresh-second-aligned-UTC>
   --manifest-out <new-external-path>`, deterministic seed 42, and the selected
   OpenAI settings. Preparation captures settings without constructing a provider;
   use network denial and a non-secret offline placeholder where the settings
   loader requires a nonempty key. The database-name guard alone does not prove
   ownership, and seed mutation precedes manifest validation. On preparation
   failure, preserve safe evidence and clean up only the resources created by
   that attempt; do not offer a failed environment for authorization.
4. **Verify and retain immutable identities.** Capture clean source SHA, dependency
   manifest hash, actual Python/installed package versions and provider-runtime
   fingerprint; Alembic/PostgreSQL versions; seed/reference, table/anomaly counts
   and canonical seeded-data digest; exact dataset/catalog/canary identities from
   [policy](v1-quality-gates.md#evaluation-v2-and-the-text-to-sql-contract); and
   `queryops-evaluation-environment-v2` fingerprint. Revalidate read-only and retain
   the exact DB/source/runtime/settings unchanged through qualification. Reference
   age must be at most 24h at each start (5-minute future-skew tolerance). Expiry
   or drift requires stopping and fresh offline preparation/authorization, never
   extending or silently substituting an identity. Do not reset tests or run
   concurrent state-changing QA against this DB.
5. **Authorize and run the canary stage separately.** Return exact prepared
   identities, settings, call/attempt exposure, fresh cost uncertainty and evidence
   locations for explicit authorization of exactly three fixed 10-case canary
   invocations. Use the existing [runner](../../backend/scripts/run_evaluation.py)
   with explicit `--provider openai --model gpt-6.1-terra --suite canary
   --environment-manifest <matching-path>`, no filters. Inspect each persisted run
   before the next; do not replace failed runs, retry/resume a partial sequence,
   switch models or add runs without new authorization. SDK retries remain part
   of the selected profile. The fixed membership/order is owned by
   [selection.py](../../backend/app/evaluation/selection.py), not a new handpicked
   suite.
6. **Gate full40 and readiness.** Three matching canaries must pass applicable
   thresholds/security/zero-defect gates and have identical outcomes, pass/fail,
   contract observations and failure stages. Inspect the read-only
   `check_v1_readiness.py --run-id <third-canary-id> --json` stability section;
   overall readiness may remain incomplete until full40. Only after stability
   passes, obtain explicit authorization for one matching unfiltered `--suite full`
   invocation, all 40 exactly once. Preserve run IDs/safe per-case evidence and
   usage; require automated readiness `ready` and independently verified exact-main
   CI. Do not infer success from exit code zero or an aggregate score.
7. **Complete subsequent manual QA.** Preserve qualification evidence first, then
   follow the entire [checklist](../qa/v1-manual-qa.md) on the same unchanged
   candidate: User/Manager/Analyst/Admin permissions, direct-route denials and exact
   scopes; actions/approvals/audit/notifications; dashboards/editing/refresh/CSV;
   light/dark, desktop/390×844 mobile, keyboard/focus and error/empty/loading/partial
   states. Record tester/method/browser/time/SHA/safe manifest identity. Paid free
   queries/clarification checks need a separate explicit manual-QA call budget.
   QA mutations do not permit more qualification against altered data. Only then
   may local synthetic V1 completion be assessed; shared/production is out of scope.

## Operator gates and blockers

The runner validates environment/settings before provider construction, not before
each HTTP dispatch; prevent concurrent drift operationally. It does not enforce
canary stability before full40, and a completed run can exit zero despite failed
quality gates. Ordinary semantic/provider errors may continue within that run;
existing fatal setup/auth/persistence failures terminate it. The readiness service
does not fetch GitHub CI. Operators must inspect persisted evidence and verify CI
externally; W6c single-use reservation/journal protections are not reused by V2.

Proposed authorization must stop **before another paid run** on identity/freshness
failure, failed/incomplete/unstable qualification, security or renderer/conformance
defects, or evidence-persistence failure. Required unestablished result comparisons
remain non-qualifying under existing policy. Do not claim these operator stage
stops abort an in-flight case or are new automated gates.

Before freeze: explicit owner decisions/offline authorization, reviewed merged
reconciliation, exact final-main CI, and any owner-required hard-bound work must
be complete. No additional product defect is established as a mandatory fix by
the two historical misses. Fresh environment, live authorization, qualification
and full manual QA are subsequent mandatory gates, not evidence already earned.
