# QueryOps AI — Development History

## 2026-11-01 — W6b Candidate Availability implementation candidate

Implemented on `feature/m10-w6b-candidate-availability` from verified main
`722e6a0`, after approval commit `bd93569`. The existing authorized ranked core,
lexical evidence and intent metadata remain intact. A bounded authorized graph
and atomic concept/metric/rule dependency bundles add optional availability;
selection order reuses description scoring, including zero-score definitions,
with deterministic ties and final canonical IDs. No prompt/model/catalog,
dataset, thresholds, schema or RLS changes. Mock unsafe metadata now reports only
lexical entity references rather than all available tables; its unchanged
Evaluation expectation passes. This was a diagnosed integration correction,
not an adjustment of expected answers or scores.

Two specialized non-author implementation contributors independently compared
retrieval/budgets and authored PostgreSQL/API adversarial regressions. One owner
implemented production changes and reconciled contracts/tests/docs; their helper
inspection is not the separate independent final acceptance review.

Implementation commit `9f537a3` is pushed in
[draft PR #68](https://github.com/Daniel23sh/queryops-ai/pull/68). Final-head CI
run links, actual new-file collection and browser case counts belong to that PR's
validation section; PR creation is not proof that those gates passed. No merge
or independent acceptance is claimed.

Frozen known-corpus coverage: 40/69 → 69/69, entities 56/91 → 91/91,
relationships 7/13 → 13/13, concepts 30/40 → 40/40, rules 3/6 → 6/6,
metrics 3/3 unchanged. No positive regressions, maximum 16,000 bytes.
Five legacy empty-entity controls fail literally as authorized options become
available; all forbidden IDs and lexical negatives remain absent. See the
[Hebrew decision](../audits/2026-11-01-candidate-availability-he.md) and
[replay artifact](../audits/2026-11-01-candidate-availability-results.json).

Local evidence: original focused regression 4 failed/3 passed before, then all
7 passed; final focused semantic/ownership/candidate suite 161 passed. Actual
PostgreSQL 16.14/API candidates 14 passed, zero skips; unchanged Mock evaluation
plus these candidates 15 passed. Complete PostgreSQL backend suite (excluding the
separate action release gate) **1,965 passed, zero skips**; exact action release
gate **20 passed, zero skips**. Ruff, Pyright (zero
errors), compilation, diff and changed Markdown target checks passed. The initial
sandbox-blocked full run was aborted and is not valid test evidence. The first
network-enabled full run found the Mock metadata defect (1,960 passed/1 failed);
the corrected final run passed unchanged Evaluation expectations.

CI and PR-head evidence are recorded in the PR handoff after execution. The
existing full-pytest jobs collect both new files; the corpus regression explicitly
forbids Git-history access so shallow CI works. Existing real PostgreSQL Chromium
Ask Data free-query/save-card/export and governed flows provide browser regression
coverage when their CI run passes. No paid provider, qualifying Canary/Full40,
held-out/W6c validation or release qualification was performed. Independent final
review remains pending and the branch must stay unmerged.

## 2026-11-01 — Output Identity merged; Candidate Availability authorized

PR #67 merged at `722e6a092b53dd58b7f9779393273ed13cc70c33`. Local/fetched main,
remote merge metadata and ancestry were verified on a clean checkout. The
independent re-review of corrected head `f43d630` closed the P2 browser-selection
finding after checking both cases actually executed in CI and all required gates.
The owner approved Candidate Availability only as a separate W6b follow-up; W6c,
W7, prompt/model tuning and paid runs remain unapproved. Historical unmerged or
pending-review statements below describe their dated handoffs.

## 2026-11-01 — W6b independent review and CI selection correction

A fresh non-author review of [PR #67](https://github.com/Daniel23sh/queryops-ai/pull/67)
at `8fc585a` returned **CHANGES REQUIRED** for one P2: the two new
`output-identity.spec.ts` cases inherited `@m8-primary`, were excluded from the
general E2E job and were absent from the five explicit M8 Primary commands.
The original six green jobs therefore did not prove those two cases ran in CI.
The reviewer independently ran focused PostgreSQL/security checks and both real
Chromium cases, and reported no additional runtime or security finding in scope.

The correction adds the existing Chromium spec as the sixth sequential command
in M8 Primary, after `dashboard-integrity`; it changes no application behavior,
fixture guard, authorization or release threshold. Locally, Playwright collected
exactly two output-identity cases; the preceding dashboard suite passed three
cases and then both output cases passed against a fresh disposable PostgreSQL
instance. A GitHub-style `bash -e -o pipefail` simulation verified that a failing
sixth command propagates failure, and the existing aggregate gate rejects a
failed M8 result. These checks are not a substitute for CI execution.

The corrected head must show both named cases actually executed and passed in
[PR #67 checks](https://github.com/Daniel23sh/queryops-ai/pull/67/checks), together
with all required gates. The PR description records the exact-head run and test
evidence after verification. Independent re-review remains a separate pending gate;
the PR is intentionally unmerged and V1 release qualification remains incomplete.

## 2026-11-01 — W6b deterministic output identity candidate

Implementation `1667afc` on `feature/m10-w6b-deterministic-output-identity`
starts from verified PR #66 merge `dac8031`; scope approval is `b73ec48`.
[Draft PR #67](https://github.com/Daniel23sh/queryops-ai/pull/67) is an unmerged
implementation candidate. At its initial handoff, no independent final acceptance
review had been performed; the later review and correction are recorded above.
Current PR/review status belongs in PROJECT_PLAN.md.

### Design, compatibility and boundaries

The renderer retains unique PostgreSQL labels and qualifies only collisions as
`entity_id__column` / `aggregation__id`. It reserves compatible labels, applies
ASCII folding/63-byte limits and allocates bounded suffixes in semantic-identity
order, so row values and selection reordering cannot change a field's assigned
label within the same selected output set. Long/case-varying aggregation labels
match cursor and provenance names. No provider alias field, new plan algebra,
generalized naming framework, migration or persisted result rows were added.

The shared executor checks cursor labels before mapping records, even when empty.
Ambiguous saved SQL now fails safely with a generic public error, empty output,
no successful refresh run and no successful export audit. Such Cards must be
regenerated from an authorized fresh query; SQL is not guessed or rewritten.
Existing conformance, provenance and result comparison support the generated
aliases without code or scoring changes. See the
[output contract](../development/semantic-ownership-migration.md#deterministic-output-identity--m10-w6b-contract).

The coordinator owned production code and renderer/core PostgreSQL regressions.
A separate agent independently designed consumer coverage and owned only the
new guarded synthetic fixture, API tests and browser spec. Its contribution
verifies consumers; it is not the reserved independent final review.

### Evidence

- Four renderer regressions failed before implementation on the baseline:
  duplicate ID/name fields, generated-name reservation/aggregation collisions,
  case folding and 63-byte truncation. The canonical hard-005 PG regression also
  failed against an archived, unmodified `dac8031` backend (`id,id`). The corrected
  runtime preserves unequal device/user IDs and passes the unchanged V2 semantic
  and result contracts on the same governed snapshot. No provider was called.
- Complete disposable-PostgreSQL backend suite: **1,940 passed, zero skipped**
  (`/tmp/queryops-w6b-backend.xml`); exact action security suite separately:
  **20 passed, zero skipped** (`/tmp/queryops-w6b-actions.xml`). Focused 142-test,
  nine-case core PG and six-case consumer runs are included/overlap these totals.
- Frontend: **318 tests / 49 files passed**. Two new Chromium flows passed against
  actual isolated APIs/PostgreSQL, without route mocks. They check both IDs,
  NULL/fanout, table headers, inferred aggregate bar values, persisted manual table
  mode after reload, real CSV content/formula protection and absence of browser
  result snapshots. Unexpected browser/page errors are test failures.
- Consumer API tests cover duplicate names and field/aggregate collisions,
  source→save→reload→repeated refresh→CSV, administrator versus current scoped
  viewer, restricted export denial and ambiguous legacy failure without data or
  successful side effects. Core tests cover empty results, quoted unique legacy
  labels, explicit NULL extension, actual cursor/provenance normalization,
  output reordering and field/aggregate ORDER BY with colliding labels.
- Ruff, Pyright (zero errors/warnings), compilation, browser-spec ESLint and Node
  type check passed. Fresh migrations reached `0010_disable_inactive_user` and
  Alembic check found no new upgrade operations. Validation used three task-owned
  PostgreSQL 16.14 clusters only; no normal application database was reset.

No paid calls, Canary/Full40, blind held-out model-quality claim, W6c, candidate
retrieval improvement, prompt/model tuning or W7 work is included. Full manual
release QA and independent final approval remain open; passing CI does not qualify
V1. Existing source-based evidence invalidation remains in force.

## 2026-11-01 — W6a merged; narrow W6b authorized

PR #66 merged at `dac8031bd368f0d17fb94818369cd3071bf8160e`. Remote merge metadata,
fetched main and diagnostic ancestry were verified on a clean checkout. The owner
approved deterministic output identity only for W6b, with V3 evidence and an
unmerged candidate PR; independent final review is a separate approval gate.
Candidate retrieval, prompt/model tuning, W6c, W7 and paid evaluations remain
out of scope. Historical W6a unmerged statements below describe its handoff.

## 2026-11-01 — W6a semantic diagnosis and independent review

[PR #66](https://github.com/Daniel23sh/queryops-ai/pull/66) contains the completed,
intentionally unmerged investigation from main `b1f03a4`. Approval `36591a1`,
diagnostic evidence/report `a31eb0d`, reproducibility corrections `b1852b8`;
documentation/review handoff follows. No production semantics, tests, prompts,
catalog, frozen dataset, threshold or release gate changed. Private planning files
were untouched. No paid calls, qualifying runs or V1 release claim were made.

Three specialists investigated candidate availability, business composition and
algebra/evaluator contracts. The coordinator and a fresh non-author reviewer
replayed 79 candidate cases, 18 composition and 19 algebra probes. Focused tests:
480 passed with seven PG skips; the PG relational suite separately passed 33 with
zero skips, also independently repeated. Counts overlap and are not additive.

The reviewer found two P2 diagnostic defects: missing algebra source/data/catalog
enforcement and an obligatory temporary test-log/static-pass claim. Both were
corrected before DB access/log-free replay and independently re-reviewed at
`b1852b8`; no blocking finding remains. Assertions cover a subset of composition
outcomes; the reviewer separately compared all records. Current provider quality,
positive inactive-user NULL coverage, browser/CSV collision propagation and fresh
held-out quality remain unverified.

The [Hebrew report](../audits/2026-11-01-w6a-semantic-diagnosis-he.md) prioritizes
deterministic output identity for the first bounded W6b decision: hard-005's two
required ID fields collide in SQL labels and lose a value during mapping. F14
candidate misses are reproducible; medium-009's omission mechanism is reproduced
only through handwritten plans, not current provider selection. Canonical
hard-004 works on a nonempty fanout fixture. Candidate/context changes remain a
separate decision; broad prompt/model/algebra changes are not justified. W6b and
the exact eight-question live experiment proposal require separate approval.

## 2026-11-01 — W4 + W5 merged; W6a diagnosis authorized

PR #65 merged into main at `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`. GitHub
merge metadata, fetched origin/main, ancestry and identical reviewed implementation
were verified before the next task. This supersedes only the prior unmerged
handoff status; its evidence and limitations remain historical.

The owner approved W6a investigation only, on clean branch
`investigation/m10-w6a-semantic-diagnosis` from that main. Production semantics,
frozen evaluations and quality gates must remain unchanged. Three independent
specialists investigate retrieval, interpretation/composition and algebra/runtime/
comparison, followed by fresh review of the consolidated decision. No paid calls
or W6b implementation is approved. Tracked worktree was clean and ignored planning
files remain untouched.

## 2026-11-01 — W4 + W5 implementation and independent review

Branch `feature/m10-dashboard-evaluation-integrity` starts at verified main
`e20fa7c9193efdb7ab5de6b01a80a3f39b4e30d3`, after PR #64 merged. Scope approval
was recorded at `5436c25` before implementation. Separate owners implemented W4
frontend/editor/mapping and W5 backend identity/telemetry; the coordinator reviewed
and integrated them, implemented the nullable-usage UI and maintained CI/docs.
Commits: W5 `515e057`, W4 `f13c4ad`, UI/CI `5acfb1e`, timeout correction
`178f132`. [PR #65](https://github.com/Daniel23sh/queryops-ai/pull/65) is open
against main and intentionally unmerged. This is a reliability handoff, not V1
release qualification. Current approval/status belongs in PROJECT_PLAN.md.

### W4 decisions

- A narrow layout-draft hook owns the server baseline, unsaved layout and expected
  layout version separately from refreshed Dashboard/Card metadata. Known own
  mutations reconcile the current card set without discarding retained positions;
  new cards are placed below the draft. Unexpected version changes, collisions
  and incompatible edited sizes retain the draft and require explicit resolution.
  Save uses the draft baseline for the existing backend CAS contract.
- Save/cancel, transient refresh/save failure, explicit discard and navigation
  have composition coverage. Failed metadata refresh keeps the draft; access
  denial/not-found clears protected Dashboard metadata. A delegating popstate
  guard is registered before BrowserRouter and is active only for a dirty editor,
  so rejecting Back does not unmount/remount and erase it. Same-page skip/hash
  navigation preserves focus/draft without a discard prompt. No router or state-
  management framework replacement was introduced.
- Numeric primary values are retained for KPI/charts regardless of aliases such
  as total/max/target. Only a genuine gauge value/target pair excludes its
  denominator from primary measures. Exact-42 aliases, percentages, gauges,
  compatible/incompatible manual choices and auto mappings have regressions.
  Layout/config contain no raw result-row snapshots.

### W5 decisions and qualification invalidation

- Environment identity is now `queryops-evaluation-environment-v2`. One shared
  `queryops-provider-runtime-v1` digest covers allowlisted exact provider/model,
  official endpoint, reasoning effort, output cap, timeout, retries, actual Python
  and installed provider/HTTP, validation, SQL/database and seed dependency
  versions. It excludes credentials, arbitrary environment values, prompts and
  rows. No new schema or historical evidence migration/backfill was required.
- Manifest creation captures settings without constructing/calling a provider;
  validation, frozen descriptors, persistence, stability and readiness use the
  same identity. Read-only checks compare current OpenAI candidate configuration
  and installed versions without needing an API key. Historical v1/missing or
  malformed identity is incomplete/ineligible. Matching old canary/full evidence
  cannot qualify a changed current configuration. Dataset versions, baselines,
  quality thresholds, source/data/catalog checks and fail-closed rules remain.
- Production-owned HTTP hooks count dispatches, including retries/redirects, in a
  per-call ContextVar reset in finally. Injected clients lacking observation
  report unknown physical attempts. Logical calls and safe failure latency/
  observed token counters are distinct; incomplete or overflowing totals remain
  null, never fabricated zero or clipped exact counts. No response body is
  retained. The 64/call and 2,560/full-run representation bounds accommodate
  existing redirects and do not change retry configuration or HTTP behavior.
- Authorized usage API fields are nullable. UI shows unavailable counts as
  `Not available`, keeps measured zero, and exposes only API-returned projections.
  It also handles legitimate attempt counts above the previous 120/run bound.

### Independent findings and corrections

The fresh non-author reviewer inspected the full combined diff and connected
paths. The review found an **inherited P2 timeout defect**: when configured to
5 seconds, the installed SDK could substitute 600-second read/write/pool defaults
because the explicit timeout was supplied only to its HTTPX client. A new actual-
dispatch test failed for 5 seconds while adjacent 4/6/45 cases passed. Commit
`178f132` restores the explicit SDK argument; all four phases now match the frozen
configuration. Independent re-review and a repeated 161-case focused backend
selection passed. The reviewer also identified the living quality-gate document's
stale environment-v1 requirement, now aligned to v2 and explicit old-evidence
invalidation. No unresolved finding remained.

During coordinator review, response-stream timeouts were kept outside the
telemetry JSON catch to preserve SDK failure/retry semantics, and token overflow
was made unavailable rather than silently capped. Controlled stream/overflow
regressions passed before final review. No provider or retry budget was increased.

### Verification and limits

- W4 red tests reproduced eight draft/mapping failures. Full frontend validation
  passed **318 tests in 49 files**, ESLint, both TypeScript checks and build.
  The usage-UI test failed before the unavailable-versus-zero presentation change.
- W5 broad PostgreSQL subsystem selection passed **540 tests, zero skips**;
  dedicated manifest/failed-usage persistence selection passed **48, zero skips**.
  Actual installed-SDK local transports cover 500→success, terminal failure,
  timeout (including response-stream failure), malformed structured output and
  redirects. Settings/dependency changes, identical configurations, strict old/
  malformed identity rejection and current-model binding are covered.
- After the timeout correction, CI-equivalent disposable PostgreSQL selections
  passed **1,921 backend tests + the exact 20 action-security cases**, zero skips,
  failures or errors. From `backend/`, with the guarded disposable URL/opt-in:

  ```bash
  .venv/bin/pytest tests/test_action_security_release.py -q -rs
  .venv/bin/pytest --ignore=tests/test_action_security_release.py -q -rs
  ```

- Chromium passed **36 flows**: three new composed desktop/numeric/mobile editor
  cases, existing actions 2, access 2, scoped Evaluation 9, result delivery 8 and
  general 12. New W4 flows use real APIs/PostgreSQL, exact synthetic 42-value
  fixtures, competing layout versions, offline retry, rejected/accepted Back and
  skip-link/hash navigation. Existing general Evaluation fixtures remain UI-only
  evidence. The final SDK-only correction does not alter Mock browser behavior;
  exact-final-revision CI reruns the complete graph.
- Fresh Alembic upgrade/current/check reached `0010_disable_inactive_user` with
  no model diff/new operations. Ruff, zero-error/warning Pyright, compilation,
  Markdown-link and diff checks passed. The known chart chunk-size warning remains
  non-blocking. Three task-owned disposable PostgreSQL clusters isolated W5,
  combined regression and browser data from normal application resources.
- Independently executed evidence: **161 backend tests, 80 frontend tests, one
  PostgreSQL persistence case**, plus the actual timeout dispatch probe. The
  reviewer inspected broader results but did not independently rerun every
  browser/security suite. Notes: `/tmp/queryops-integrity/independent-review.md`.

Logs/JUnit/browser evidence are temporary under `/tmp/queryops-integrity`; final
PR CI provides retained exact-revision evidence. Documentation follows the reviewed
runtime commit. No paid calls, qualifying live Canary/Full40 sequence, W6 work,
deployment or completed manual release QA occurred. Historical evaluations remain
readable but cannot bypass the new qualification identity. V1 stays incomplete;
the recommended next package after owner approval/merge is separately scoped W6a
semantic diagnosis, not automatic implementation or a paid release sequence.

## 2026-10-31 — W2a + W3 merged; W4 + W5 authorized

PR #64 merged into main at `e20fa7c9193efdb7ab5de6b01a80a3f39b4e30d3`. GitHub
merge metadata, fetched origin/main, reviewed-head ancestry and identical merged
implementation were verified before the next batch. This supersedes only the
previous unmerged handoff status; its evidence and limitations remain historical.

The owner authorized W4 + W5 only on clean branch
`feature/m10-dashboard-evaluation-integrity` from that main. Separate owners will
handle frontend editing/values and backend qualification identity/telemetry, with
combined validation and a fresh non-author final review. No W6, paid provider,
qualifying Canary/Full40 or automatic merge is authorized. The tracked worktree
was clean; ignored private planning files remain untouched.

## 2026-10-31 — W2a + W3 implementation and combined verification

Branch `feature/m10-evaluation-reads-result-delivery` starts at verified main
`8cb9c8d55921454337316fb2e1ef9b8be4a6b1a2`, after PR #63 was confirmed merged
and its implementation present. Two independent implementation owners handled
W2a reads/tests/browser fixtures and W3 backend/provenance/security tests. The
coordinator reviewed both and implemented frontend/CSV/visualization integration.
Identifiable commits: W2a `4f6cf80`, W3 backend `6623d04`, frontend/CI integration
`01fbc8a`. [PR #64](https://github.com/Daniel23sh/queryops-ai/pull/64) was opened
against main and remains unmerged; current approval and merge status belong in
PROJECT_PLAN.md.

### Decisions

- W2a replaces only the latest-run JOIN/DISTINCT with correlated `EXISTS`, so
  PostgreSQL never compares `EvaluationRun.summary` JSON for equality. Run
  ordering, 100 distinct candidates, dataset identity validation, result parsing,
  exact scoped visibility and safe projections remain unchanged. No JSONB
  migration, permission expansion or read-service redesign was needed.
- W3 reuses existing server-owned QueryRun validation metadata. Fresh SQL
  validation and authorization still run; only consistent original bound fields
  matching the freshly validated outer limit are restored. SavedQuery/Card links
  and repeated refreshes preserve that provenance. No SQL rewriting, larger cap,
  new persistence table, raw-row snapshot or evaluator auxiliary evidence is used.
- Delivery `complete` means all rows of the **validated SQL answer**, including
  an intact input LIMIT, were delivered. It does not prove natural-language
  interpretation, business correctness or underlying population exhaustion.
  Evaluator answer-bound/comparison/readiness rules remain independent and
  unchanged. Executor/payload/deadline limits and missing provenance remain
  distinct: a reached safety bound or acquisition row cap is `safety_limited`;
  payload/deadline or legacy/malformed provenance is `unknown`.
- Exactly 100 returned rows with `truncated=false` does not establish full
  delivery of a safety-bounded population. Conversely an intact SQL top-100 can
  be delivered completely. A top-500 Card can be partial under its 100-row fetch
  cap while the separately authorized CSV delivers all 500 requested rows.
- CSV stays ordinary header/data records. Safe completeness/count headers,
  partial/unknown filename suffixes and fresh-response UI notices communicate
  limitations without contaminating data rows. CORS exposes only those safe
  headers plus Content-Disposition. Current-viewer execution/RLS, restricted
  export policy, SQL validation, formula protection, filenames and successful
  export auditing remain in force.
- Table Cards disclose ten shown versus returned rows and can expand all already
  returned rows. Chart/status/KPI subsets use their actual renderer row limit;
  their notice is separate from database delivery completeness. No further rows
  are queried by expansion. W4 draft/value-mapping changes were not included.

### Verification on `01fbc8a`

All database mutation/reset experiments used four newly created disposable
PostgreSQL 16.14 containers, with separate W2a, W3, combined-suite and browser
databases. Normal application data and ignored local planning files were untouched.

- W2a original Manager/Analyst empty reads reproduced HTTP 503; corrected real
  PostgreSQL tests passed 13/13, with existing API regressions 75/75. Coverage
  includes all five shared-loader endpoints, hidden-run versus missing 404,
  visible-only counts, malformed/duplicate results, dataset identity, tied
  ordering and the 99/100 candidate boundary with multiple matching case rows.
- W3 focused API/unit tests passed 157; executor/Card/export PostgreSQL tests
  passed 53 with zero skips; Query service/API and evaluator evidence/scoring
  consumer tests passed 201. New provenance units passed 23 and new delivery
  PostgreSQL flows passed 10 as part of those selections. The actual pipeline
  uses 620 synthetic licenses: original runtime execution, run export, real
  save-card API, two refreshes, Card export and audit/persistence inspection.
- Below/at/above cap, input top-100/top-500, safety clamp, LIMIT 0 and legacy
  metadata cases pass. Mismatched provenance and legacy 11/24-row results remain
  unknown. Exact scope revocation after a successful scoped export denies
  refresh/run/Card export without delivery headers, protected metadata or a new
  success audit. SavedQuery/Card/QueryRun and audit assertions reject raw rows.
- Combined CI-equivalent PostgreSQL selections passed **1,876 backend tests +
  the exact 20 action-security cases**, zero skips/errors/failures. Commands from
  `backend/`, with guarded disposable test environment:

  ```bash
  .venv/bin/pytest tests/test_action_security_release.py -q -rs
  .venv/bin/pytest --ignore=tests/test_action_security_release.py -q -rs
  ```

- Frontend **304 tests in 49 files**, ESLint, both TypeScript checks and build
  passed. Four visualization regressions failed before implementation and passed
  after correction; download tests distinguish fresh export states from earlier
  source state and treat missing/invalid metadata conservatively.
- Chromium passed **33 flows**: new actual-PostgreSQL scoped Evaluation 9 and
  delivery 8, plus existing actions 2, access/workflow 2 and general 12. The new
  flows use real backend APIs with no route mocks; the existing general
  Evaluation UI fixtures remain UI-only evidence. Delivery tests inspect the
  downloaded CSV data/counts/filename, response headers and browser notices, and
  access row 11 at 390×844. The initial table-11 test assumed auto inference would
  choose Table; it correctly chose Bar. The fixture now explicitly persists a
  manual Table via the real API; no product behavior was changed to satisfy it.
- Fresh Alembic upgrade/current/check reached `0010_disable_inactive_user`, with
  no new operations/model diff. Ruff, zero-error/warning Pyright, compileall and
  diff checks passed. No schema migration was introduced. The existing charts
  chunk warning remains non-blocking.

The guarded state-changing CI lane now runs actions → access → scoped Evaluation
→ result delivery sequentially, preserving fixture isolation. Logs/JUnit and
browser artifacts are temporary under `/tmp/queryops-delivery`; exact final PR
CI evidence will be retained by GitHub. A fresh-context non-author reviewer
examined the full `8cb9c8d..01fbc8a` diff and connected source/consumer paths,
independently passed **46 backend/PostgreSQL tests and 50 frontend tests**, and
found no actionable blocking or optional finding. The reviewer explicitly
examined the product bounded-SQL delivery versus independent evaluator proof
boundary. No review correction was required. Review notes/logs are under
`/tmp/queryops-delivery/independent-review.md` and `independent-*.log`.
Documentation-only reconciliation follows the reviewed runtime head; final PR
CI is required before merge. No paid provider, Canary/Full40, release qualification, threshold or
historical baseline change, W4/W5 implementation or deployment occurred.

## 2026-10-31 — W2a + W3 authorized after W1 + W2 merge

PR #63 merged into main on 2026-10-29 at
`8cb9c8d55921454337316fb2e1ef9b8be4a6b1a2`.
Before beginning the next batch, GitHub merge metadata, fetched `origin/main`,
ancestor checks and the identical reviewed implementation tree were verified.
This supersedes only the previous handoff's unmerged status; its evidence and
limitations remain historical records.

The owner authorized W2a + W3 only, on a clean branch
`feature/m10-evaluation-reads-result-delivery` from that main. The tracked worktree
was clean; ignored planning files remain untouched. The intended handoff is an
unmerged PR after PostgreSQL/browser verification and a fresh independent review.
No W4/W5 or paid provider/evaluation run is authorized by this batch.

## 2026-10-29 — W1 + W2 implementation and local V3 evidence

Integration branch `feature/m10-access-workflow-integrity` starts at main
`ada818be002e918ccdbc4339137386a61354329f`. Separate implementation agents owned
Dashboard policy/routes/tests and Role Request routes/tests; the coordinator
reviewed and committed each contribution, then added frontend conflict recovery
and combined PostgreSQL/browser regressions. Commits: W1 `e997840`, W2 `22a2b01`,
integration `8ced912`. [PR #63](https://github.com/Daniel23sh/queryops-ai/pull/63)
was opened against main and intentionally remains unmerged. Main is unchanged;
this is a handoff, not V1 completion. Current approval status belongs in
PROJECT_PLAN.md.

### Decisions and behavior

- **W1:** one `department_scope_is_assigned` policy now governs Dashboard
  visibility and create/save authorization. `AppUser.department_id` remains
  display/default metadata, never a grant. Exact secondary department and explicit
  global assignments work; missing department metadata fails closed. Personal
  ownership remains separate. Generic and compatibility Dashboard permission keys
  use the same assigned-scope checks. Card-create capabilities match actual save
  policy, including create-only versus manage grants.
- Catalog/library/detail/source, duplicate/update/archive/card/layout operations,
  Home, refresh and CSV reuse these shared policies. Current-viewer resource
  authorization, sanitized SQL, non-owner query runtime, RLS and CSV safety remain
  intact; no owner-authority shortcut or result snapshot store was introduced.
- **W2:** every supported create/approve/reject writer locks the requester's
  stable `AppUser` row with PostgreSQL `NO KEY UPDATE`; decisions then lock the
  request row. This serializes create/create even before a request exists, with
  consistent requester-before-request ordering. The weaker parent lock avoids
  cross-approver audit foreign-key `KEY SHARE` deadlocks.
- After waiting, ORM state is refreshed and actor active/effective permission,
  requester active/upward transition, pending status and explicit scope snapshot
  are revalidated. Scope ID/type/key/department must still agree. Role, assignment,
  request status and audit share one transaction. Duplicate/current-state losers
  return safe 409; persistence failures roll back and return safe 503, without raw
  driver details. Implicit Admin approval records the resolved global scope
  consistently in requested/assigned/audit data.
- A database uniqueness migration was considered unnecessary for the existing
  closed set of API writers: the requester lock protects the no-row case and all
  decision paths. Direct SQL/import writers must join this locking contract or
  introduce a reviewed database invariant. Historical duplicate pending records
  are preserved and fail closed on approval/rejection; this patch does not invent
  decisions or silently clean user data. Any existing duplicates need explicit
  operator remediation before those requests can proceed.
- Legacy requests with all explicit scope snapshot fields absent retain their
  existing current-default resolution; modern explicit snapshots fail closed on
  changes. This is compatibility behavior, not an authorization grant from
  affiliation for Dashboard access. No role workflow engine or Action Engine
  reuse was added.
- Frontend create/decision 409 responses reload current requests and never claim
  success. Failed recovery clears stale controls and asks for a page refresh.

### Reproducible validation

PostgreSQL 16.14 ran in newly created disposable containers, separate for each
implementation owner, combined regression verification and browser execution.
Normal application databases and ignored private planning files were untouched.

From `backend/`, with guarded `POSTGRES_TEST_DATABASE_URL` and
`POSTGRES_TEST_DATABASE_DISPOSABLE=1` pointing to the disposable cluster:

```bash
.venv/bin/pytest tests/test_action_security_release.py -q -rs
.venv/bin/pytest --ignore=tests/test_action_security_release.py -q -rs
.venv/bin/pytest tests/test_dashboard_scope_integrity_postgres.py tests/test_role_requests_postgres.py tests/test_access_workflow_integrity_postgres.py -q -rs
```

At implementation head `8ced912`, the first two selections passed **20 + 1,827
tests, zero skips/errors/failures**, including the three new modules: W1 22,
W2 23 and combined interaction 4. Forced contention waits were observed through
`pg_stat_activity`, not simulated SQLite locks: create/create, approve/approve,
approve/reject and reject/approve produce one winner. Other cases cover state
loaded before waiting, permission revocation, malformed/deleted/changed scope,
historical duplicates, independent cross-approvals and rollback/retry. Combined
tests preserve requester cookies across approval, rejection, stale-scope failure,
commit failure and subsequent scope revocation; rejected mutations leave no
grant or contradictory audit. A controlled flush-then-failure test rolls back
actual PostgreSQL writes before checking Dashboard denial.

The new W1 revocation regression failed against process-local original policy;
four new frontend conflict tests failed before conflict recovery was implemented.
No tracked implementation was reverted for those probes. Existing sequential
Role Request tests passed 39/39 as compatibility evidence, not concurrency proof.

Frontend: **288 tests in 48 files**, ESLint, both TypeScript checks and production
build passed. Chromium: **12 general + 2 existing governed-action + 2 new
access/workflow flows** passed with the actual mock-provider backend and disposable
PostgreSQL. New browser cases cover revocation/nondisclosure, explicit secondary
and global assignment, two admin sessions with a stale losing decision, and
original-requester session access after approval. Backend Ruff, Pyright (zero
errors/warnings), compileall and Alembic upgrade/current/check passed at head
`0010_disable_inactive_user`, with no new operations detected. No schema migration
was needed. The existing large-chart-chunk build warning remains non-blocking.

CI reuses the guarded M8 disposable lane and runs existing actions before the
new access spec; the new fixture resets only guarded synthetic data. The ordinary
browser lane still excludes all `@m8-primary` cases. Local logs/JUnit and failure
artifacts are under `/tmp/queryops-access`, with owner logs under
`/tmp/queryops-w1-*` and `/tmp/queryops-w2-*`; they are temporary evidence, not
committed raw artifacts. CI will preserve evidence for the exact PR revision.

Fresh-context final independent review examined the complete `ada818b..8ced912`
diff and connected callers, authentication, persistence models, failure paths and
tests. The reviewer authored none of the implementation and independently reran
all **49 new PostgreSQL regressions, zero skips**, on the idle disposable W2
cluster. No blocking security/correctness finding or required correction remained.
The reviewer explicitly accepted the current writer-lock invariant and legacy
scope compatibility with the limitations above; those are not database-wide
uniqueness or frozen-legacy-intent claims. Review log:
`/tmp/queryops-access/reviewer-focused.log`. Documentation-only reconciliation
follows the reviewed runtime head; final PR CI remains required before merge.
No paid provider request, qualifying evaluation, release threshold/baseline change,
unrelated M10 fix or production deployment occurred. W2a/W3 and later packages,
full manual release QA and V1 qualification remain outside this handoff.

## 2026-10-29 — W1 + W2 batch authorized

The owner explicitly expanded the next implementation from W1 to W1 + W2 only:
Dashboard Exact-Scope Authorization and Atomic Role Requests. A clean integration
branch `feature/m10-access-workflow-integrity` was created from validated main
`ada818be002e918ccdbc4339137386a61354329f` after fetching origin; tracked worktree
was clean. Existing ignored local planning changes were preserved.

Separate implementation owners were assigned distinct Dashboard and Role Request
files/tests. Combined PostgreSQL/browser verification and a fresh-context final
security/correctness review are required. The requested handoff is an **unmerged
PR** for final approval. W2a/W3 and later work remain outside this batch. This entry
records approval and start, not completed implementation or release qualification.

## 2026-10-28 — W0 integrated; W1 approved

[PR #61](https://github.com/Daniel23sh/queryops-ai/pull/61) merged the reviewed
feature head `a3759d8f3e22dc16e762b4876c234a784991d65a` into `main` at
`f23099c1a7d9ffaad8bc2c445a6551d77ffa5cb1`. All five deterministic jobs and the aggregate
V1 Deterministic Release Gates check passed on the PR head. The original feature
branch was removed locally/remotely only after verifying its head is an ancestor
of main; original unique work remains protected by the local and remote
`codex/archive-m9-bounded-result-2d7796c` ref. No force-push or baseline rewrite.

The prior W0 record below describes the decision, fixes and local evidence at the
pre-merge checkpoint. This entry supersedes its pending-integration status only.
The October audit remains unchanged as dated evidence. Current documentation was
reconciled to M10 and W1; old private planning bodies remain historical with clear
supersession notices and were not committed. No unrelated M10 fix was implemented.

W1 — Dashboard Exact-Scope Authorization is now the approved next implementation.
Role-request concurrency, scoped Evaluation JSON DISTINCT, derived completeness,
UI defects and semantic/provider-identity work remain open. No live provider call
or release qualification occurred. All W0 disposable containers/volumes and local
app processes were removed after verification; existing project data was untouched.

## 2026-10-28 — W0 bounded-result disposition: retain with corrections

W0 compared remote main `a64d1fa9ebae3abf2a9cd87d27fa0f47e29b1c94` with the
original bounded-result commit `2d7796c056ce2c234989dae010b4c34f71758a9d`. The
branch had not been integrated or superseded. Its unique work was protected by
local recovery ref `codex/archive-m9-bounded-result-2d7796c`; no history was
rewritten or force-pushed. Phase 1 direction documents were committed separately
at `4894672` before the branch treatment was selected.

Selected option B: keep the implementation with narrowly justified corrections.
The evaluator solves a real defect: equal capped prefixes do not establish equal
populations, while differing valid prefixes need not mean different answers.
Shared REPEATABLE READ/UTC context, validator-authorized outer safety-bound
widening, role/RLS enforcement, bounded row/time/payload acquisition, explicit
unestablished state and safe projections are necessary parts of that proof.

Alternatives evaluated:

- Unchanged merge preserves valuable work but leaves reproducible cache, proof
  and consumer defects; rejected.
- Conservatively label every bounded comparison unknown: smaller, but loses
  correct measurable answers within the fixed budget; rejected.
- Accept equal prefixes or raise/remove production caps: fails correctness or
  resource safety; rejected.
- Split/rewrite: no independent component sequence reduces the coordinated
  runner/scoring/persistence/UI contract risk; discarding tested invariants is
  costlier than the focused corrections. Preserve the original commit and put
  corrections in a separate reviewable commit instead.

Corrections (new regressions were observed failing before fixes):

- Cache only table DataResource metadata, preventing column metadata from
  replacing table authorization; PostgreSQL regression proves denial.
- Recognize EOF below a supported input LIMIT without widening that limit or
  accepting nested/offset/volatile comparisons; semantic bound mismatch still fails.
- Accept identical valid exactly-N top-N answers; differing unresolved cutoff
  members remain unestablished. Removed the redundant unconditional veto helper.
- Render the legitimate three-canary `stability_comparison_unestablished` state
  as Incomplete, while contradictory count/reason combinations remain unavailable.
- Reject list/dict states/digests and oversized numeric durations at persisted
  boundaries without TypeError/OverflowError or fabricated qualification.

Independent correctness, runtime/security and contracts reviews approved the
corrected scope. Local verification: 1,776 PostgreSQL backend tests plus the
20-case action security suite passed without skips; 284 frontend tests, Ruff,
zero-error/warning Pyright, compileall, ESLint, both TypeScript checks and build
passed. The final additional numeric guard passed the focused 253-case selection
and independent malformed-shape probes; GitHub will rerun the complete graph on
the exact committed revision. General Chromium flows passed 12/12 and guarded M8 flows 2/2. A separate
Chromium probe rendered the actual backend-shaped three-run unestablished
payload as Incomplete (readiness response routed as a fixture, not persisted
integration evidence). Fresh Alembic
upgrade/current/check reached 0010 with no model diff. The existing charts chunk
warning remains non-blocking. Detailed temporary logs are under `/tmp/queryops-w0`.

No provider call, qualifying evaluation sequence, historical baseline change,
RLS/role grant change, cap/budget/threshold weakening or schema migration was
introduced. No unrelated W1–W9 fix was bundled. W1 scope revocation, W2 role
races, W2a scoped JSON DISTINCT reads, W3 derived delivery and other audited
product/semantic/identity gaps remain open. Integration status at this checkpoint
is **pending GitHub CI and merge**, not a completed release.

## 2026-10-28 — M10 direction adopted; W0 opened

The owner selected local synthetic IT Operations V1 as the completion target and
authorized M10 — Product Reliability & V1 Completion. The October project audit
is dated evidence, not release qualification. Existing modular/query/action/RLS
architecture is retained; major new capabilities and shared/production deployment
are deferred. The historical milestone sequence no longer authorizes the next
feature. The detailed [M10 roadmap](../development/m10-completion-roadmap.md) splits
semantic work into diagnosis, targeted correction and independent validation.

W0 was opened to independently resolve `fix/m9-bounded-result-evaluation` at
`2d7796c` against current main. No integration/discard decision had been made at
this documentation checkpoint. Older implementation evidence below records work
done on particular revisions, not proof that the branch was merged or released.

## Approach 3 bounded-result evaluation correction

Implemented from audited main
`a64d1fa9ebae3abf2a9cd87d27fa0f47e29b1c94`. Production execution retains its
existing safety limit and delivered rows. Evaluation can widen only a structurally
proven outer safety bound, under one authorized read-only `REPEATABLE READ`
transaction and the versioned `queryops-bounded-result-evidence-v1` resource
budget. Complete evidence can qualify a correct safety-limited delivery;
insufficient evidence remains explicit, non-qualifying `unestablished` evidence.

The implementation keeps comparison state in metrics without a database migration,
preserves legacy returned-count delta fields and adds clear read-model aliases.
Delivery completeness is separate from correctness and appears in product and
evaluation UI without exposing auxiliary rows or invented totals. Readiness policy
`queryops-v1-readiness-v2` rejects required unestablished comparisons and historical
evidence. V2 dataset and fixed-canary digests changed deterministically to
`6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f` and
`83dadd97b819003e9e6aa20b4487affc8a3c926cd7ca3d2672c85225b4ae3fc2`.

Verification completed:

- Full offline gates: Ruff, zero-error/warning Pyright, compilation, ESLint, both
  TypeScript checks and production build passed; **1,580 backend tests passed**
  with 199 expected environment-gated skips, and **282 frontend tests passed**.
- The two V3 guarded disposable-PostgreSQL selections passed **20** and **1,754**
  tests with zero skips. After the final three pre-commit corrections, the full
  second selection passed **1,759** tests with zero skips.
  Focused evaluation tests additionally covered arbitrary safety subsets,
  differing populations, exact cap, 1,000/1,001 evidence boundaries through the
  runner, structural bounds, duplicates, `DISTINCT`, grouping, aggregates,
  ranking ties, transaction time, concurrent commits, RLS/context mismatch,
  deadlines, payload accounting and original-stage failures.
- Five Chromium Evaluation flows passed. Alembic reported
  `0010_disable_inactive_user` at head and no model/schema changes. `git diff
  --check` passed.
- The final three pre-commit corrections preserve successful execution across
  QueryRun persistence/context teardown failures, distinguish SQL exhaustion
  from population completeness and comparison proof from context compatibility,
  and use one exact payload-set definition. A fresh-context focused independent
  review found no remaining blocker in those three areas. No live provider call,
  canary, release environment, candidate, user
  database, migration, push, PR or release operation occurred.

The correction does not resolve medium-009 provider semantic reliability,
hard-004 aggregate-grouping provider/runtime ownership, other tracked DISTINCT
enforcement gaps, pagination/export, provider tuning or release qualification.

## Evaluation V2 semantic correctness correction

Based on audited `75568dc5f6cef5f541eac1b357e8809828133547`, with no initial
source drift. Corrected only medium-006, hard-004 and hard-006 plus evaluator
comparison logic. [Correction details and identity transition](../evaluation/v2-semantic-corrections.md)
record the proof boundaries and preserved semantics. V2 ID/version and canary
membership remain fixed; dataset/canary digests changed deterministically.

Verification completed:

- 166 targeted evaluation/provenance/structural/conformance tests passed,
  including 21 new synthetic semantic-correction regressions.
- 10 PostgreSQL evaluation tests passed, including six new baseline/representation
  cases. Nonempty fixtures verify distinct counts across two memberships, the
  five/six threshold boundary, time window and failed-event filter.
- `./scripts/check`: 1,514 backend tests passed; 169 environment-gated skips;
  280 frontend tests passed; Ruff, Pyright, compilation, ESLint, both TypeScript
  checks and production build passed. Existing non-blocking Vite chunk warning
  remains.
- Full isolated PostgreSQL backend suite: **1,683 passed, zero failures/errors/skips**,
  including existing security, RLS, action and conformance coverage.
- Alembic upgrade/current/check passed at `0010_disable_inactive_user`; no model
  or schema changes detected. The newly created disposable PostgreSQL 16 container
  was used exclusively; existing databases were untouched.
- Final fresh-context independent review found no remaining actionable defects.
  Review caught and resolved numeric-tolerance and explicit-output preservation
  issues before completion. Author diff review and Markdown-link checks passed.
- Historical V1 is byte-identical; medium-009 is unchanged; ignored planning
  documents are neither tracked nor staged.

No live provider calls, live canary, or qualifying release claim. Prior evidence
is non-qualifying after this source/dataset change. A separate freeze, authorization
and complete evidence sequence remain necessary.

This document preserves useful implementation history for archaeology. It does not authorize new work and is not a source of current project status. See [`PROJECT_PLAN.md`](../../PROJECT_PLAN.md) for the active objective and [`AGENTS.md`](../../AGENTS.md) for permanent repository rules.

## PR57 — Planner Ownership Implementation Checkpoint

Implemented against main `be218b43b8c7120a043d3113c7562ef5e9293168`.
Free-question lexical matches now retain candidate context, not plan obligations;
structural hints are Suggested only. Selected catalog definitions and deterministic
proofs remain binding. The [ownership document](../development/semantic-ownership-migration.md)
records the cutover and explicitly versioned diagnostic compatibility.

Offline validation: `./scripts/check` passed with **1,493 backend tests passed /
163 environment-gated skips**, **280 frontend tests passed**, Ruff/Pyright,
compilation, lint, both TypeScript checks and build clean. Vite's existing
non-blocking chunk-size warning remains. PR53 v2 reruns retain 20 accept/accept,
15 reject/accept and 4 reject/reject cases; PR52 legacy-hint reruns retain six
free-query conflicts. V2 digest remains
`a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0`.
Thirty-six independent IT Operations fixture projections fit below 16KB (maximum
13,894 bytes); synthetic complete-candidate overflow remains fail-closed.

Checkpoint review found diagnostic packaging and ambiguous historical-reproduction
claims; the adapter now ships under `app.diagnostics` and reruns explicitly use
current proofs with historical hint axes. Independent regression and fresh-context
final V3 reviews found no unresolved actionable findings. No database-dependent
contract changed, no live provider/evaluation run occurred, and this is not
release qualification or PR58 authorization.

## PR56 — Candidate/path Completeness (merged)

PR56 merged as `be218b43b8c7120a043d3113c7562ef5e9293168`. Grounding now
retains the complete authorized relationship graph for connected components
containing at least two semantic anchors, including direct/indirect, equal-length
and optional alternatives. It no longer selects a preferred connector tree.
Connector entities remain candidates only and do not import unrelated concepts,
metrics or examples. Optional context trims first; complete candidates that cannot
fit the unchanged 16KB budget fail closed. The provider still selects a tree and
PR55 validates it. Production English ownership was deliberately left for PR57.

## PR55 — Relational Validation Checkpoint

On 2026-09-06, Phase 0 verified clean HEAD and main ancestry at
`6af16a4eb002b5b1b56619d6fe4b477d799c87bc` (PR53 and PR54 merged).
The [relational guarantees and limitations](../development/relational-semantic-validation.md)
record aggregate types, renderer compatibility, selected-tree metric multiplicity,
and null-sensitive metric conformance. Ad-hoc business grain remains undeclared;
English interpretation remains a future PR57 responsibility.

Validation on the PR55 implementation:

- `./scripts/check`: passed; Ruff and configured Pyright clean, Python compilation
  successful, backend **1,443 passed / 163 environment-gated skips**, frontend
  **280 passed**, lint/type checks/build passed. Vite reported its existing
  non-blocking chunk-size warning.
- Focused plan/composition/catalog/renderer/conformance, PR52/PR53,
  grounding/provider-stub, V2 dataset/scoring/readiness selection:
  **508 passed / 7 PostgreSQL skips**.
- New relational tests with the disposable database: **33 passed**.
- New relational plus query-engine/query-API, SQL-executor/security, query-runtime
  role and RLS PostgreSQL selection: **96 passed, zero skips/errors/failures**,
  verified from JUnit XML. A fresh disposable PostgreSQL 16 container on local
  port 55435 was necessary: the shared cluster's pre-existing action runtime role
  correctly blocked its migration guard. Existing roles were not modified to
  bypass that guard.
- `git diff --check`, changed-document link checks, frozen PR52/PR53 audit
  reproduction, and V2 integrity passed. V2 digest remains
  `a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0`.
- AST comparison confirmed unchanged SemanticPlan/observation definitions and
  legacy Required Intent/FK-PK enforcement. Provider, grounding, domain catalog,
  evaluation assets/scoring/readiness and PR53 fixture paths have no diff.

The fresh-context V3 reviewer found no actionable issues and independently ran
the new non-PostgreSQL cases. No provider calls occurred. This is engineering
validation evidence, not release qualification or authorization to start PR56.

## PR53 — Offline Ownership Migration Evidence

On 2026-09-05, Phase 0 verified remote/local main and clean HEAD at
`4263fc5b29dea9d2ff8367cfefd1eb219cab239d` (PR52 merged). PR53 uses the existing
validator twice on the same supplied plan, removing only question-derived
GroundedResultIntent in an offline projection copy. No runtime, provider,
SemanticPlan, SQL, authorization, V2, or release-policy code changed.

The [migration report](../development/semantic-ownership-migration.md) records
the authority inventory, 32 independent supplied-plan fixtures / 24 question
strings / 39 comparisons, and future ownership. Outcomes: 20 accept/accept,
15 reject/accept, 4 reject/reject. Changed outcomes include 7 false constraints,
7 useful NL-derived checks, and 1 unresolved coincidental rejection. The report
explicitly distinguishes PR54 relational proofs from PR56 interpretation duties.

Validation from `backend/` used `PYTHONDONTWRITEBYTECODE=1` and disabled pytest's
cache provider. PostgreSQL/E2E database opt-in variables were unset:

- `.venv/bin/pytest -p no:cacheprovider tests/test_semantic_ownership.py -q`:
  **28 passed**.
- Focused PR53 + PR52 structural adapters/conformance + semantic
  grounding/plan/composition/catalog + provider stubs/config + renderer/conformance
  + evaluation dataset/query-set/scoring/stability selection: **488 passed**.
- `.venv/bin/pytest -p no:cacheprovider tests/test_v1_readiness.py tests/test_v1_readiness_cli.py -q`:
  **46 passed**.
- `.venv/bin/pytest -p no:cacheprovider -q`: **1,417 passed, 156 skipped**.
  This is the default non-PostgreSQL suite, not PostgreSQL or release evidence.
- `.venv/bin/ruff check app scripts tests/test_semantic_ownership.py`: passed.
- `.venv/bin/pyright`: zero errors/warnings; explicit Pyright over the three new
  scripts also reported zero errors/warnings.
- `git diff --check`, local Markdown target checks, frozen V2 digest, PR52 audit
  reproducibility, and byte-unchanged runtime/provider/V2/release paths: passed.

A fresh-context independent V3 reviewer inspected the complete implementation
and report, independently reproduced the 28 tests and report counts, and found
no actionable issues. No provider calls, database execution, or SQL execution
were performed. PR54 and runtime ownership migration were not started. PR53
requires PR review/merge handling; this is engineering evidence, not a release
or merge verdict.

## PR52 Chunk 2 — Local Foundation Checkpoint

On 2026-09-03, the foundation implementation was completed locally on diagnostic
baseline `9eb094ab14d8ae5ef05e5a0d5a52cb8ce13287af`. It adds query-engine-owned
structural declarations, separate comparison policy, query-engine adapters, and
a narrow Evaluation V2 contract adapter. Existing primitives were reused without
extraction. No execution/scoring integration or Chunk 3 harness was added. See
[the foundation design](../development/semantic-intent-foundation.md).

Focused validation: 47 new tests passed. Existing semantic-plan/composition,
grounding, catalog, OpenAI-provider stub, evaluation-scoring/dataset,
query-evaluation-set, renderer, and semantic-conformance suites: 362 tests passed.
Ruff passed on all new Python files; explicit Pyright coverage of the four new
application modules reported zero errors or warnings. Independent V3 review
identified and verified correction of one named-metric knownness issue: empty
explicit aggregate declarations remain known empty, with scalar grain, and a
differential scorer regression covers the boundary. No blocking review findings
remained. No provider/API calls or PostgreSQL tests were performed; no
database-dependent behavior was modified. This is local engineering evidence,
not a merge or release verdict.

## PR52 Chunk 3 — Local Offline Audit Checkpoint

On 2026-09-04, the offline V2 structural-conformance harness produced its first
deterministic report. It loaded all 40 unchanged V2 cases and the real domain pack,
built grounding with synthetic scope-only contexts and an in-memory authorized
schema projection, and compared required and suggested intent separately. The
machine-readable report and text CLI do not execute SQL, use a database, call a
provider, persist evaluation records, score cases, or participate in readiness.
Generated output was written only to `/tmp` during validation and was not added to
the repository.

The report retained the frozen V2 digest
`a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0`.
Across all 40 cases it reported 26 compatible, 9 conflict, 5 not applicable,
and 0 unavailable. Among 35 answerable cases, required coverage was 1 complete,
9 partial, 24 none, and 1 structurally not applicable; suggested coverage was
0 complete, 2 partial, 32 none, and 1 not applicable. Among 29 answerable free
queries, compatibility was 23 compatible and 6 conflict; required coverage was
1 complete, 6 partial, 21 none, and 1 not applicable. Ordering was unavailable
from the current grounding model in four free-query contracts.

Validation added 16 harness tests; all 63 PR52 tests passed. The relevant existing
semantic, provider-stub, evaluation, renderer/conformance, readiness, and stability
suites passed 410 tests. Ruff passed for all PR52 Python files, and explicit
Pyright checks on the new application modules and audit script reported zero
errors or warnings. No PostgreSQL validation was needed because the harness has no
database behavior. This is diagnostic engineering evidence, not a release verdict
or authorization to modify grounding or frozen evaluation data.

PR52 finalization recorded the six answerable free-query conflicts and their
architecture-level mechanism classes in the foundation document. The complete
backend unit suite passed 1,389 tests with 156 database-dependent tests skipped;
Ruff and Pyright remained clean. No runtime, prompt, provider, scoring, readiness,
renderer, semantic-conformance, or frozen V2 asset changed.

## Milestone Timeline

| Milestone | Outcome | Merge references |
| --- | --- | --- |
| 0 — Repository foundation | Monorepo and local project foundation established. | PR #1, `deb71a7` |
| 1 — Database and seed foundation | SQLAlchemy/Alembic foundation, product and IT Operations schemas, deterministic seed profiles. | PRs #2–#5, ending `ecd5b87` |
| 2 — Auth, roles, and permissions | Demo session backend, permission model, auth UI, and role-upgrade workflow. | PRs #6–#9, ending `deb75fb` |
| 2.5 — Access Context Foundation | Added access scopes, user-scope assignments, data resources, `UserAccessContext`, `AccessDecision`, and policy evaluation; followed by hardening. | PRs #10–#11, ending `c4321d1` |
| 3 — RLS and security foundation | Added scope-aware PostgreSQL RLS and transaction-local RLS context. | PR #12, `66c03de` |
| 4 — Query Engine backend | Added domain-pack loading, templates, provider abstraction, SQL safety, restricted query runtime, governed execution, QueryRun persistence, and PostgreSQL security tests. | PR #13, `49719ef` |
| 5 — Ask Data | Closed backend contract gaps, added typed frontend clients, Ask Data UI and query flow, role-aware SQL/diagnostics, and the Tailwind product shell. | PRs #14–#19, ending `2866afc` |
| 6 — Dashboards, cards, and export | Added dashboard/card persistence and UI, controlled CSV export, current-viewer refresh, layout ordering, and audited Admin restricted-export policy. | PRs #20–#24, ending `3845429` |
| 7 — Product UX and dashboard redesign | Added routing/navigation, role-aware Home and dashboard browser, responsive dashboard editor/visualizations, and final Ask Data UX hardening. | PRs #25–#28, ending `4ddeded` |
| 8 — Actions, approvals, and audit | Added deterministic Action Engine contracts, two governed IT Operations actions, approval execution, restricted action runtime, audits, notifications, requester/approver UI, and release security gates. | PRs #29–#35, ending `408190f` |
| 9 — Evaluation and V1 readiness implementation | Added evaluation data/scoring, runner/persistence, role-aware metrics UI, explicit OpenAI mode, readiness policy, semantic planning/conformance, plan-only deterministic SQL rendering, Evaluation V2, and stability gates. Implementation is merged; release evidence remains a current concern, not history. | PRs #36–#46, ending `757187a` |

## Merged Pull Request Index

Commit abbreviations identify first-parent merge commits on `main`.

| PR | Work | Merge |
| ---: | --- | --- |
| 1 | Milestone 0 setup | `deb71a7` |
| 2 | Milestone 1 database foundation | `b590e4f` |
| 3 | Milestone 1 product schema | `dd9cfdb` |
| 4 | Milestone 1 IT Operations domain schema | `caeae8e` |
| 5 | Milestone 1 deterministic seed data | `ecd5b87` |
| 6 | Milestone 2 auth/session backend | `bdc37f0` |
| 7 | Milestone 2 roles/permissions backend | `b4f73f5` |
| 8 | Milestone 2 auth UI and role-aware sidebar | `c614c1a` |
| 9 | Milestone 2 role-upgrade flow | `deb75fb` |
| 10 | Milestone 2.5 access-context foundation | `f138c2a` |
| 11 | Access-context hardening | `c4321d1` |
| 12 | Milestone 3 RLS/security foundation | `66c03de` |
| 13 | Milestone 4 Query Engine backend | `49719ef` |
| 14 | Query backend compliance fixes | `6270cc3` |
| 15 | Ask Data API clients | `befc40b` |
| 16 | Ask Data shell | `1403e3f` |
| 17 | Ask Data query integration | `29b9bb6` |
| 18 | Ask Data role-aware SQL/diagnostics and tests | `eb55c51` |
| 19 | Tailwind UI foundation and frontend redesign | `2866afc` |
| 20 | Dashboard/card backend foundation | `a497bdc` |
| 21 | Dashboard/card UI | `7f74d53` |
| 22 | CSV export backend | `3ead4f4` |
| 23 | Card refresh and CSV export UI | `5b4d04c` |
| 24 | Card reorder/layout persistence | `3845429` |
| 25 | Product shell, routing, and navigation | `743eb52` |
| 26 | Role-aware Home and dashboard browser | `db2adf5` |
| 27 | Dashboard editor, grid, and visualizations | `8701ba0` |
| 28 | Ask Data responsive polish | `4ddeded` |
| 29 | Action persistence and engine contracts | `38bbe41` |
| 30 | Reclaim-license preview/request flow | `c703034` |
| 31 | Approval execution, audit, and notifications | `096267c` |
| 32 | Disable-inactive-user action | `2619d5e` |
| 33 | Requester Actions UX | `0286427` |
| 34 | Approvals, Audit, and Notifications UX | `73531f2` |
| 35 | Milestone 8 E2E/security completion | `408190f` |
| 36 | Evaluation dataset/scoring foundation | `a21cdce` |
| 37 | Evaluation runner, persistence, and CLI | `800b2f4` |
| 38 | Role-aware Evaluation metrics API | `fd1b8cc` |
| 39 | Role-aware Evaluation workspace | `f8990b7` |
| 40 | Governed real-LLM evaluation mode | `695be13` |
| 41 | V1 quality gates and readiness | `c6691a2` |
| 42 | V1 release-validation preparation and semantic catalog | `54c0c2f` |
| 43 | Required/Suggested Intent provider contract | `216cea5` |
| 44 | Minimal semantic grounding graph | `49a43fa` |
| 45 | Plan-only provider and deterministic SQL renderer | `ec0c812` |
| 46 | Evaluation V2 and stability release gate | `757187a` |

## Important Historical Decisions

### Access and database enforcement

- Milestone 2.5 established effective permissions plus assigned scopes as the application authorization model.
- Milestone 3 made PostgreSQL RLS and transaction-local viewer context a second, independent enforcement layer.
- Milestone 4 introduced the non-owner, read-only `queryops_query_runtime` role. Later dashboard refresh and export paths retained current-viewer authorization, SQL validation, this restricted role, and RLS.
- Milestone 8 introduced the separate, narrowly granted `queryops_action_runtime` role for deterministic domain mutation. The query role remained read-only.
- Product `app_users` and IT Operations `directory_users` were deliberately kept as different identities; no attribute-based identity inference was accepted.

### Query and dashboard evolution

- Approved templates remained deterministic and provider-free throughout Query Engine evolution.
- Query results could be saved as cards, but raw rows were not accepted as durable dashboard config/layout snapshots. Refresh and export re-execute under the current viewer's authority.
- Milestone 6 added an explicit Admin restricted-export permission. It may override only an otherwise non-exportable but still queryable resource; missing or non-queryable resources remain hard denials.
- Milestone 7 added versioned responsive layouts, safe visualization shapes, soft dashboard archive, and source visibility gated by `can_view_sql`.

### Actions

- V1 intentionally implemented only `reclaim_unused_license` and `disable_inactive_user`.
- Actions use bounded client selectors only. The backend independently reads and revalidates current targets through authorization and RLS.
- Preview, approval, optimistic/idempotent one-winner execution, current-state revalidation, domain/application audit, and database notifications were retained as one governed lifecycle.
- Execution remained synchronous and notifications database-only. No queue, automatic retry/rollback action, external delivery, or LLM-selected mutation target was added.

### Evaluation and provider contract evolution

- PRs #36–#39 added the original 40-case V1 dataset, synchronous runner and sanitized persistence, five role-aware read-only metrics endpoints, and a read-only Evaluation workspace.
- PR #40 added one explicit opt-in OpenAI Responses API provider while leaving Mock as the default. Provider prompts used allowlisted schema/semantic context and excluded identities, rows, scope keys, evaluator answers, and action targets.
- PR #41 added fail-closed readiness policy `queryops-v1-readiness-v1`, deterministic release gates, a read-only CLI/API projection, and tracked QA/evidence documents.
- PR #42 added semantic catalog v3, deterministic semantic grounding and conformance, release-environment provenance, and a reviewed `itops-medium-009` baseline correction justified by the pre-existing non-compliant-device definition. It did not produce qualifying live evidence.
- PR #43 separated binding Required Intent from non-binding Suggested Intent. Suggested Intent cannot independently reject a valid plan.
- PR #44 selected the minimal deterministic relationship graph needed by selected semantic components.
- PR #45 superseded the earlier provider-SQL contract: the provider now returns one structured `SemanticPlan`; the backend validates it and renders SQL deterministically, with no repair call or fallback.
- PR #46 preserved historical V1 and added the reviewed 40-case Evaluation V2 semantic contracts, a fixed 10-case canary, exactly-three-run stability assessment, matching full-run rules, failure-stage measurement, planner-integrity checks, and zero-tolerance renderer/conformance defect gates.

## Selected Historical Verification and Review Evidence

These counts describe particular completed revisions and must not be treated as current test counts.

- M8 PR3's final snapshot passed 818 disposable-PostgreSQL backend tests and the action concurrency/runtime suites. Four CodeRabbit passes reported 20 findings (2 Critical, 16 Major, 2 Minor); all were fixed with regression coverage. The final follow-up review was manual because another CodeRabbit run was unavailable.
- M8 PR7's final snapshot passed 907 disposable-PostgreSQL backend tests, the exact 20-case action suite, 247 frontend tests, general and isolated M8 browser flows, and migration/no-diff checks. Its manual release review fixed four Minor issues and found no remaining actionable issue.
- M9 PR4's final snapshot passed 1,001 disposable-PostgreSQL tests, 266 frontend tests, production build, and five Evaluation browser flows. A manual review fixed one fail-closed run-consistency issue and two Minor issues.
- M9 PR5's final snapshot passed 1,046 disposable-PostgreSQL tests, 268 frontend tests, provider/runner/API/CLI safety checks, and relevant browser flows. No live call was made. A manual review fixed an ambient SDK configuration/proxy-isolation issue.
- M9 PR6's final snapshot passed 1,092 disposable-PostgreSQL tests, 274 frontend tests, deterministic backend/frontend/browser/migration/static-analysis gates, and the aggregate GitHub release gate. A manual security/release review fixed one Major fail-closed evidence issue and three Minor issues.
- M9 PR7's implementation snapshot passed 1,236 disposable-PostgreSQL tests, 375 focused Text-to-SQL tests, 274 frontend tests, browser and migration gates. Codex Security scan `f7036ba0-9e86-40c4-9e2d-0177908bbc31` covered 17 changed runtime/configuration surfaces and reported zero findings.
- M9 PR11's final implementation snapshot passed 1,420 isolated-PostgreSQL tests plus the exact 20-case M8 suite, 1,284 default backend tests with expected PostgreSQL skips, 280 frontend tests, 14 browser flows, fresh migration/no-diff checks, Ruff, zero-error/warning Pyright, compileall, ESLint, both TypeScript checks, production build, and `git diff --check`. Manual branch review found no remaining actionable issue; CodeRabbit was unauthenticated, so no CodeRabbit result was claimed.
- PR #46 merged at `757187ace074d83b075ba2550f8dd6a2c50d64a1` on 2026-09-02. GitHub reported successful Backend, PostgreSQL Security, Frontend, E2E, M8 Primary E2E, and V1 Deterministic Release Gates checks for both the PR and final `main` runs.

## Superseded or Archaeological Notes

- Early planning references to RLS, Actions, Evaluation, dashboards, or real-provider support as future work describe their original sequencing, not current implementation status.
- Early PRD text describing provider-generated SQL and multi-attempt self-correction is superseded by PR #45's one-call plan-only provider contract and deterministic backend renderer.
- The original Evaluation V1 dataset and its old Mock score remain historical evidence. V2 is the release-evidence dataset; neither dataset may be tuned from observed live outcomes.
- Historical PR-specific "do not begin the next PR" instructions expired when those PRs merged. Their durable security properties were retained in `AGENTS.md`; their temporary file/scope boundaries are not active rules.
- Review-tool availability statements and test totals were point-in-time evidence, not permanent requirements.

## Detailed Historical References

- [`docs/evaluation/m9-pr11-implementation-report.md`](../evaluation/m9-pr11-implementation-report.md)
- [`docs/evaluation/v1-quality-gates.md`](../evaluation/v1-quality-gates.md)
- [`docs/evaluation/v1-readiness-report.md`](../evaluation/v1-readiness-report.md)
- [`docs/security/m8-release-test-matrix.md`](../security/m8-release-test-matrix.md)
- Git first-parent history on `main`, especially merge commits listed above.
