# M10 — Product Reliability & V1 Completion

Direction adopted 2026-10-28. Current approval/status belongs only in
[PROJECT_PLAN.md](../../PROJECT_PLAN.md). This is the authoritative detailed
completion roadmap; the [audit](../audits/2026-10-26-project-audit-he.md) is a dated
evidence baseline, not a living task tracker. Historical milestones remain in
[development history](../history/development-history.md) and local planning files.

## Product boundary and architecture

Finish the existing local IT Operations V1 with deterministic synthetic data.
Preserve React/TypeScript/Vite, FastAPI, SQLAlchemy/Alembic/PostgreSQL, the domain
pack, provider abstraction, one structured SemanticPlan call, deterministic SQL,
SQL safety/conformance, non-owner runtime roles, RLS, current-viewer authorization,
and deterministic actions with preview/approval/audit. Legal execution does not
prove business correctness or complete delivery.

Free-query language interpretation belongs to the planner. Lexical and structural
matches provide non-binding candidates/guidance; selected catalog definitions and
relational/security proofs remain binding. Required Intent is binding only when
provided by an independently trusted structured source; ordinary production free
questions currently have no such source. Historical provider SQL, multi-attempt
semantic repair and a second binding English parser are superseded.

Only the two existing actions are in V1. Actions remain synchronous and
notifications database-only. Real identity/shared deployment, production hosting,
SSO, multi-tenancy, a second domain, more actions, NoSQL adapters, queues,
schedulers, external notifications and multi-agent runtime are deferred. Local
synthetic V1 must still enforce its authorization and concurrency contracts;
calling it a demo does not waive correctness.

## Evidence and open problems

The October audit on `2d7796c` recorded 1,779 PostgreSQL backend tests, 282 frontend
tests and 14 Chromium flows passing. Independent probes still reproduced exact-
scope dashboard bypass, role-request races, JSON DISTINCT failure in scoped
Evaluation reads, discarded editor drafts, missing visual values and hidden
partial results. The single diagnostic `gpt-5.6-luna` canary passed 9/10;
medium-009 executed successfully but omitted a business rule. hard-004 passed
that run; do not treat every historical suspicion as a proven defect.

These are dated observations, not proof of the current/final revision. Provider
configuration identity and usage telemetry need work before qualifying evidence.
No current automated `ready` or complete manual release QA is established. W0 selected retention with narrow corrections after independent review. The
[decision record](../history/development-history.md) compares alternatives; actual
Git integration status and the active task remain in PROJECT_PLAN.md.

## Work packages

S/M/L are relative effort, not calendar estimates. Each package must close its
specific invariant with executable evidence, review proportional to
[validation risk](validation-model.md), and an explicit remaining-limit record.
W0 established the baseline; current approval belongs in PROJECT_PLAN.md. Later
packages describe direction, not permission to batch unrelated fixes into one PR.

| Package | Scope and intended result | Dependencies / acceptance / verification | Effort and decisions |
| --- | --- | --- | --- |
| W0 — Baseline Resolution | Assess all M9 bounded-result changes; retain, correct, split or replace on evidence; preserve recoverable unique work; integrate the selected baseline | Compare current main/merge base and remote state; verify caps, same-snapshot evidence, role/RLS, budgets, correctness/unknown outcomes, persisted compatibility and projections; independent V3 review; record actual commits and integration state | M; choose minimum justified design, not minimum line count |
| W1 — Dashboard Exact-Scope Authorization | Audit F1: remove affiliation fallback across policy/callers/capabilities | After W0; revoked assignments deny catalog/library/detail/source/create/save/duplicate/update/archive/card paths; explicit second/global assignments still work; PostgreSQL + browser, refresh/export cannot expand authority | M/V3; preserve personal ownership contract |
| W2 — Atomic Role Requests | Audit F2: one pending request and one terminal winner; consistent role/scope/audit | PostgreSQL forced create/create, approve/approve and approve/reject interleavings; one safe conflict; atomic rollback; current-state revalidation; migration checks if DB invariant added | M/V3; choose lock/CAS/constraint using existing patterns |
| W2a — Scoped Evaluation Reads | Audit F13: eliminate DISTINCT over JSON without broadening visibility | Independent of W2; PostgreSQL empty/visible/inaccessible scoped run APIs, Admin control and real browser without route mocks; preserve nondisclosure/order/limit | S/V2; EXISTS or ID-only deduplication, no speculative schema migration |
| W3 — Reliable Result Delivery | Audit F5/F8: preserve safe answer-bound/delivery provenance through saved card, refresh and CSV; truthful displayed row counts | Explicit top-N versus safety cap; PostgreSQL population above cap; warnings survive save/refresh/download; no raw-row persistence or cap removal; API/browser/CSV tests | M/V3; choose bounded export disclosure explicitly |
| W4 — Dashboard Editing and Values | Audit F6/F7: preserve dirty draft during mutations; correct KPI/chart numeric mapping | Composition tests for move/resize + rename/add/remove/visualization and conflict; total/max aliases and value-target pairs display actual values; desktop/mobile E2E | S–M/V2; guard or narrow reconciliation, no new state framework |
| W5 — Evaluation Identity and Usage | Audit F4/F10: immutable secret-free provider/runtime fingerprint; honest calls/attempts/failed usage | Before qualifying paid runs; changed reasoning/token/runtime config fails matching; unchanged config passes; old missing evidence incomplete; transport retry/failure tests, persistence/readiness/stability regressions | M/V3; version contract and invalidate evidence deliberately |
| W6a — Semantic Diagnosis | Audit F3/F11/F14: independently measure candidate recall, business composition, DISTINCT/grain/grouping and failure stage | Freeze diagnostic config and independent contrasts/held-out paraphrases; identify general root causes and supported algebra; report uncertainty and bounded run budget; no fixes or dataset tuning in this package | M; diagnosis ends with one justified narrow correction scope |
| W6b — Targeted Semantic Correction | Implement only W6a-supported candidate/context/prompt/runtime correction | Depends W6a; deterministic/adversarial and PostgreSQL regressions, no per-case IDs or weakening baselines; preserve planner ownership and safety | M, possibly L/V3; compare model change only if diagnosis supports it |
| W6c — Independent Semantic Validation | Fresh review and held-out validation of W6b | Depends W6b and W5 for qualifying identity; original V2 unchanged except independently justified contract correction; no tuning from held-out results; classify model, renderer, conformance and comparison separately | M/V3; failures return to a bounded diagnosis, not an endless tuning loop |
| W7 — Explicit Local Release Boundary | Audit F9: enforce explicit demo-only behavior and reject unsupported auth modes; align product docs | Local synthetic target is decided; no real identity implementation required for V1; unknown/non-demo mode cannot silently expose demo login; session/permission negative tests | S/V3; shared/production identity remains future scope |
| W8 — Reproducible Validation | Safely orchestrate disposable services/fixtures and reproducible dependency/runtime evidence | Test guards reject user DB; clean run reproduces CI graph and cleans its resources; consistent hostnames; real scoped Evaluation integration; document local liveness/readiness limits | M; use existing commands, avoid a new framework |
| W9 — Freeze and V1 Completion | Close all V1 blockers, final CI, matching canary×3 then full40, complete manual QA and evidence | Depends W1–W8 including W2a/W6c; same unchanged source/data/config; existing thresholds and zero-defect gates; full QA roles/themes/mobile/keyboard/error/partial; exact model/run authorization before paid sequence | M/V3; failed/unknown evidence never qualifies |
| W10 — Optional Cleanup / Measured Performance | Audit F15 legacy dashboard deletion, chart loading or list hot paths only when justified | After core reliability; preserve useful active-path tests, verify imports/dependencies before deletion; measure performance before optimizing | S–M; not a release blocker absent demonstrated impact |

W1 is the first implementation priority after W0. W2/W2a, W3/W4 and W5 can then
be sequenced with minimal overlap. W6a can diagnose while other fixes proceed,
but qualifying evidence must wait for W5 and independent W6c validation. W9 does
not absorb unbounded redesign; unresolved blockers return to their package.

## Definition of Done for local synthetic IT Operations V1

1. Supported scope and demo boundary are explicit; unsupported auth modes fail
   closed. No claim of production/shared identity or deployment readiness.
2. Effective permissions and exact assignments govern every resource, including
   metadata/source/derived outputs. Revocation and secondary/global positive
   cases pass actual PostgreSQL/API/browser tests; no identity inference.
3. Role and action decisions are atomic and one-winner under real concurrency;
   state, grants, audit and notifications agree, including retry/failure/expiry.
4. Templates and free questions produce useful correct results; safety-limited
   delivery and visual subsets are disclosed throughout query/card/CSV. Drafts
   survive normal editing; tables and visualizations faithfully show values.
5. Exact source/provider/config/data/runtime identities match three stable canary
   runs and full40; existing security/quality thresholds are unchanged, renderer
   and conformance defects zero, required unestablished comparisons non-qualifying.
   Independently held-out semantic evidence supplements the small fixed dataset.
6. Complete real integration and manual QA cover four personas, empty/loading/
   failed/denied/partial states, light/dark, desktop/mobile (390×844), keyboard,
   focus/return and documented accessibility checks. Mocks do not replace DB/API
   evidence. No unexplained browser errors or hidden data loss.
7. Fresh migrations/no-diff, non-owner roles/RLS/locking, safe disposable validation
   and reproducible setup pass. Local recovery/setup limitations are documented;
   production backup/restore operations remain future deployment scope.
8. Final CI and recorded manual QA refer to the same unchanged candidate. Passing
   CI alone, milestone completion, high aggregate score or a diagnostic provider
   run never establishes readiness.

## Sources of truth

- `PROJECT_PLAN.md`: current state, active scope, next approved work.
- This roadmap: M10 scope/dependencies/acceptance and local V1 boundary.
- `README.md`: supported behavior, setup and architecture overview.
- `AGENTS.md` and validation model: durable workflow/security/verification rules.
- `docs/evaluation/` quality gates and `docs/qa/`: detailed runtime release contracts
  and evidence, subordinate to no unrecorded threshold changes.
- Audit and development history: dated findings and completed decisions.
- Ignored local planning specifications: detailed domain/product references;
  superseded status/architecture notes are historical, not a second task backlog.
