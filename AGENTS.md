# QueryOps AI — Agent Instructions

These instructions apply to all AI coding agents working in this repository.

## 1. Read Before Coding

Before making code changes, always read:

1. `README.md`
2. `PROJECT_PLAN.md`
3. `AGENTS.md`
4. Local planning documents under `docs/planning/`, if available

The `docs/planning/` directory is intentionally ignored by Git. It may exist only in the local workspace and should be used as private implementation context when available.

Do not commit files from `docs/planning/`. Do not modify files under `docs/planning/` unless explicitly asked.

## 2. Milestone Source of Truth

The current development status and any active target are defined in `PROJECT_PLAN.md`.

```txt
Agents must follow PROJECT_PLAN.md and must not implement future milestone work unless explicitly requested.
```

If no milestone is active, do not infer the next milestone. If a task is outside the current approved scope in `PROJECT_PLAN.md`, stop and report the mismatch instead of implementing it.

## 3. Scope Control

Agents must:

* implement only the requested milestone or task
* keep changes small and reviewable
* avoid unplanned scope
* avoid future-proof abstractions before they are needed
* update README only when setup commands, behavior, or verification commands actually change
* preserve existing user changes
* avoid unrelated refactors

If implementation details are unclear:

1. Check `PROJECT_PLAN.md`
2. Check local `docs/planning/`
3. Choose the smallest implementation that satisfies the active milestone
4. Ask for clarification only when the ambiguity cannot be resolved from local context

## 4. Permanent Guardrails

Do not commit secrets.

Do not commit generated build artifacts.

Do not commit local environment files.

Do not commit ignored private planning documents.

Do not introduce real LLM calls before requested.

Do not silently change product scope.

Do not rewrite unrelated files.

Prefer boring, maintainable structure over clever abstractions.

## 5. Current Milestone Notes

The milestone status is defined in `PROJECT_PLAN.md`.

At the time this file was updated, the current target is:

```txt
M9 PR3 — Role-Aware Evaluation Metrics API
```

Milestone 0, Milestone 1, Milestone 2, Milestone 2.5, Post-Milestone 2.5 hardening, Milestone 3, Milestone 4, and Milestone 5 are complete under the previous scopes. Milestone 5 PR6 has been merged into `main`. M5 Ask Data and the M5 frontend redesign are complete.

Milestone 6 is complete and merged into `main`. `M6 PR1 — Dashboards/Cards Backend Foundation`, `M6 PR2 — Dashboard/Card UI`, `M6 PR3 — CSV Export Backend`, `M6 PR4 — Card Refresh & CSV Export UI`, and `M6 PR5 — Card Reordering & Layout Persistence` plus the final Admin restricted-export policy are complete. PR #24 merged PR5. Milestone 7 — Product UX & Dashboard Redesign is complete. M7 PR1 is complete and merged through PR #25. M7 PR2 is complete and merged through PR #26. M7 PR3 — Dashboard Editor, Grid & Visualizations is complete and merged through PR #27. M7 PR4 — Ask Data Redesign & Final UX Hardening is complete and merged through PR #28. Milestone 8 — Actions, Approvals & Audit is complete and merged through PR #35; verified `main` reached `408190f1cdf5710ed80a83065d65fd9cd01c4f87`. M9 PR1 is complete and merged through PR #36 at `a21cdce59f7c3cd05e3e6fec72699554ffbb9979`. M9 PR2 is complete and merged through PR #37; verified `main` reached `800b2f4006057d7a046d28da8ddb28aebc2f6176`. Milestone 9 — Evaluation, Quality Measurement & V1 Readiness is active, and only M9 PR3 is approved for implementation.

M9 follows this six-PR sequence: dataset/scoring foundation; runner/persistence; APIs/authorization; Evaluation UX; real-LLM evaluation mode; and V1 quality gates/readiness. Do not begin a later PR without explicit activation.

M9 PR1 delivered the 40-case IT Operations evaluation dataset, immutable contracts, strict independent loader, evaluator-only baseline validation, and pure semantic scoring utilities. Preserve its exact 10/15/10/5 distribution and six template-backed cases.

M9 PR2 delivered the synchronous governed evaluation runner, deterministic actor/scope resolution, restricted evaluator baselines, sanitized persistence, honest metrics, and manual MockLLM CLI. Preserve its measured 10/40 result and 4/5 security result without reinterpretation.

M9 PR3 may add only the five read-only Evaluation Metrics endpoints, centralized permission/scope visibility policy, strict safe response schemas, persisted-measurement read service, documentation, and focused/full backend verification.

M9 PR3 guardrails:

* Implement only `GET /api/v1/evaluation/overview`, `/queries`, `/actions`, `/security`, and `/dashboards`; no endpoint may start evaluation or execute SQL.
* Authorize from current effective permissions and `UserAccessContext`: User is forbidden, Manager requires department-evaluation permission and an assigned department, Analyst requires scope-evaluation permission and assigned scopes, and Admin requires global-evaluation permission plus global scope.
* Recalculate scoped totals from only visible `EvaluationResult` records. Never copy global `EvaluationRun.summary` aggregates into Manager or Analyst responses or leak inaccessible run existence.
* Use authoritative case contracts and deterministic evaluation-actor attribution to filter scope; fail closed when attribution, persisted shapes, or scope mappings are missing or inconsistent.
* Manager receives business-safe fields only. Analyst/Admin receive only explicitly allowlisted technical metadata, and SQL-adjacent metadata additionally requires `can_view_sql`.
* Never expose baseline/generated SQL, QueryRun SQL, rows, prompts, provider payloads, secrets, stack traces, raw database errors, arbitrary JSON blobs, hidden-scope totals, or internal evaluator configuration.
* Actions and Dashboards must report `not_measured`, zero measured cases, null score, and controlled reason codes; do not infer quality from product tables or query cases.
* Do not add evaluation mutation endpoints, frontend/UI, real providers, external calls, workflows, thresholds, migrations, schema/seed/permission/RLS/runtime-role changes, background infrastructure, or M9 PR4+ behavior.

M8 PR1 may add only the action persistence foundation, SQLAlchemy relationships/enums, typed deterministic Action Engine contracts, explicit fail-closed registry, pure permission/scope policy decisions, the minimum stable access-action vocabulary, and focused foundation tests.

M8 PR1 guardrails:

* Do not add action API routes, frontend code, action suggestions, real previews, approval execution, domain mutations, audit writers, notification delivery, queues, Redis, background jobs, automatic rollback, or later M8 behavior.
* Preserve existing approvals and QueryRun compatibility, notifications, role-request audits, CSV export audits, seed reset behavior, query/dashboard/export behavior, and PostgreSQL RLS policies.
* Never infer identity between `app_users` and `directory_users`. Keep `it_audit_events.actor_user_id` for directory actors and use only the new nullable `actor_app_user_id` for future QueryOps actors.
* Base policy on effective permission keys and assigned scopes, not only role names. Scoped action decisions require an exact scope key and fail closed when it is absent or unmatched.
* Keep the registry explicit and typed. Do not dynamically import user-controlled modules or accept LLM-selected records, arbitrary callables, or mutation SQL.
* Do not mutate operational rows or persist QueryRun result rows. `preview_json` is schema only in PR1.
* Migration `0008_action_engine_foundation` must upgrade from and downgrade to 0007 non-destructively, preserve existing rows, avoid RLS changes, and avoid any database reset or reseed.
* The complete 20-case action workflow suite is not a PR1 completion claim; it is completed across M8 PR3, PR4, and PR7.

M8 PR1 delivered migration `0008_action_engine_foundation`, matching models/enums/relationships, the typed inert `app/action_engine` contracts and registry, pure effective-permission/scope policy decisions, the stable action/audit access vocabulary, and focused migration/model/registry/policy/access tests. Final verification passed with 606 default backend tests plus 77 PostgreSQL-only skips, all 683 PostgreSQL-backed backend tests, SQLite and fresh temporary-PostgreSQL upgrade/downgrade round trips, Alembic no-diff checks, 188 frontend tests, the production frontend build, and diff/scope review. The temporary PostgreSQL database was removed without resetting or reseeding the existing database. No action endpoint, real preview, execution, operational mutation, audit write, notification delivery, frontend behavior, or RLS policy was added. Preserve these boundaries through review and merge; do not begin M8 PR2 without explicit activation.

M8 PR2 may add only the requester-side backend flow for `reclaim_unused_license`: deterministic preview, persisted draft, submit, safe detail, pending-request cancellation, action audit, eligible-approver notification records, and focused/full security tests. The preview lasts 30 minutes; a submitted pending approval lasts 24 hours. Explicit selectors are limited to 100 unique IDs across user and assignment lists.

M8 PR2 guardrails:

* Require authentication, CSRF, effective `can_request_action`, current `UserAccessContext`, and exact scope authorization for state changes. Detail access must fail safely for unauthorized viewers.
* Authorize `license_assignments`, `licenses`, and `directory_users` independently, then read current domain rows only through the existing non-owner read-only runtime transaction with transaction-local PostgreSQL RLS. Never use an owner-session shortcut.
* Treat client IDs as bounded selectors only. Re-query and revalidate every target; source QueryRun is owned succeeded provenance only and never supplies target rows or mutation logic.
* Never parse IDs from SQL, natural-language output, result metadata, or LLM content. Never persist generic QueryRun rows, SQL, raw emails, full Directory User rows, permission catalogs, session data, or arbitrary client JSON in `preview_json` or audit/notification payloads.
* Keep eligible, skipped, and Admin-override records mutually exclusive. `last_used_at IS NULL` is eligible/high-confidence; older than 60 days is eligible; older than 90 days is high-confidence; over 20 is a request-level Admin policy flag.
* Derive approver recipients from current effective permissions, active status, and matching/global scopes. Do not hardcode recipient role names, notify disabled/ineligible users, or infer an app-user/directory-user identity.
* Preview plus audit, submit plus approval/notifications/audit, and cancel plus approval cancellation/audit must each be atomic. Duplicate submit must create no duplicate approval or notifications.
* Do not add a migration, approval decision/execution endpoint, license mutation, `it_audit_events` domain-change write, frontend/navigation/suggestion behavior, notification read API, queue, scheduler, Redis, rollback action, real LLM provider, Supabase Auth, or M8 PR3 work.

M8 PR2 delivered the explicit reclaim handler and registry entry; strict preview/request/cancel schemas; authenticated/CSRF-protected preview, submit, detail, and cancel routes; safe deterministic snapshot persistence and validation; atomic product audit/approval/notification writes; exact current-scope resource authorization; and the existing non-owner read-only PostgreSQL RLS boundary. Final verification passed with 19 reclaim handler tests, 35 action API tests, 9 dedicated action PostgreSQL/RLS tests, 660 default backend tests plus 86 expected PostgreSQL skips, all 746 disposable-PostgreSQL backend tests, Alembic head/no-diff checks, 188 frontend tests, and the production frontend build. CodeRabbit CLI authentication could not complete after the automatic callback timed out and the manual-token fallback required user interaction, so the explicitly authorized **Manual CodeRabbit-style self-review — not a CodeRabbit result** was used. It fixed two Major findings (persisted-snapshot structural validation before writes and standardized SQLAlchemy failure handling) and one Minor Decimal normalization finding; the repeated review left no actionable issue. No approval decision, execution path, operational mutation, domain audit write, notification delivery/read API, frontend behavior, migration, or M8 PR3 work exists. Preserve these boundaries through review and merge.

M8 PR3 may complete only `reclaim_unused_license` on the backend: pending approval list/detail, reject, synchronous approve-and-execute, current-state revalidation, the dedicated scoped action runtime role and write RLS, optimistic/idempotent execution, success/failure audit, database notifications and read APIs, permission-aware audit reads, safe action timelines, and deterministic security/concurrency tests.

M8 PR3 guardrails:

* Keep `queryops_query_runtime` strictly read-only. Domain mutations must use the constant-controlled non-owner `queryops_action_runtime` role with `NOBYPASSRLS`, minimal SELECT/column-UPDATE/IT-audit INSERT grants, current approver RLS context, an UPDATE policy with `USING` and `WITH CHECK`, and an IT-audit INSERT policy with `WITH CHECK`.
* Authorize with current effective permission keys and exact assigned scopes, never only role labels. Manager cannot decide approvals; scoped approval is capped at 20 and cannot be self, override, or cross-scope; global, override, and Admin self-approval require their dedicated permissions.
* Never trust persisted preview state as current. Re-query every deterministic target ID, revalidate current assignment/user/license/scope/policy data, and never let QueryRun SQL, LLM metadata, browser data, or arbitrary JSON select or mutate records.
* Handle new Admin requirements by escalating while both lifecycle rows remain pending and without a license mutation. Ordinary eligibility drift becomes stable skipped records; an all-skipped set completes as a successful zero-execution no-op.
* Use locks plus a conditional pending-state claim so approve/approve, approve/reject, and approve/cancel have one winner. Completed, failed, rejected, cancelled, and expired actions never execute again; do not add an execution-log table.
* Keep approval, the three allowed `LicenseAssignment` field changes, domain audit, application audit, notifications, skipped counts, and completion in one transaction. On technical failure, roll back all success-side effects and persist failed status/audit/notifications separately with safe public text.
* Write one `license_removed` `ItAuditEvent` per changed assignment with `actor_app_user_id`; never place an AppUser ID in `actor_user_id` or infer a DirectoryUser identity. App audit before/after payloads contain changed fields only and serializers never expose raw metadata, SQL, rows, permissions, snapshots, driver errors, or internal failure detail without explicit global permission.
* Notification endpoints are current-recipient-only, CSRF-protected for writes, idempotent, and database-only. Audit filters cannot widen effective scope; action timelines use persisted lifecycle/audit data and safe explicit fields.
* Do not implement `disable_inactive_user`, frontend/navigation/UI, a separate Execute endpoint, external notification delivery, WebSockets, background jobs, queues, Redis, scheduled execution, automatic retry/rollback, real LLM behavior, Supabase Auth, or M8 PR4+ work.

M8 PR3 delivered migration `0009_action_runtime_role`; the non-owner action role and minimal grants; role-scoped write RLS; permission-aware approval list/detail/reject/synchronous approval execution; current-state dependency-locked revalidation; conditional claims and idempotent one-winner lifecycle behavior; deterministic reclaim mutation; atomic success and separate safe failure persistence; application/domain audit; database notifications and recipient-only read APIs; scoped/global audit reads; and safe persisted timelines. All-skipped revalidation completes as a successful no-op, while new override requirements remain pending and escalate without mutation.

Final verification passed the exact 20-case action-security suite, 8 verbose runtime/concurrency cases, 44 focused final PostgreSQL action cases, 9 disposable-database guard cases, 686 default backend tests with 132 expected PostgreSQL skips, all 818 disposable-PostgreSQL backend tests, the `0008 -> 0009 -> 0008 -> 0009` migration round trip and Alembic no-diff check, 188 frontend tests, and the production frontend build. Four completed CodeRabbit passes reported 20 findings (2 Critical, 16 Major, 2 Minor), all fixed with regression coverage. A fifth pass was rate-limited and the post-cooldown retry was rejected before launch, so the final post-fix gate used the authorized **Manual CodeRabbit-style self-review — not a CodeRabbit result** and found no unresolved actionable issue. No zero-finding CodeRabbit result is claimed. No frontend behavior, `disable_inactive_user`, worker/queue/scheduler/Redis, external delivery, retry/rollback action, real LLM behavior, or M8 PR4 work was added. PR3 is merged through PR #31; preserve its boundaries through PR4 review and merge.

M8 PR4 may add only the second V1 backend action, `disable_inactive_user`, plus the narrow Directory User action-runtime/RLS extension and focused/full security verification required to complete the V1 backend action set.

M8 PR4 guardrails:

* Reuse the existing generic preview/request/detail/cancel and approval/reject/synchronous-execution APIs. Do not duplicate the reclaim lifecycle or add a separate Execute endpoint.
* Base inactivity on current successful-login state with a deterministic 90-day boundary. Human active accounts may be eligible; recent-login and already-disabled accounts are skipped; service accounts are hard-skipped and never Admin-executable.
* Privileged humans, humans with open critical security events, and authorized cross-scope humans require Admin override. More than 20 actionable users is a request-level Admin flag only.
* Re-query and lock current users and action-specific dependencies in deterministic order. Persisted preview and QueryRun metadata are context/provenance only and never select execution targets.
* Extend `queryops_action_runtime` only with required dependency SELECT, column-level UPDATE of `directory_users.account_status` and `directory_users.updated_at`, and an exact role/scope/state RLS policy. Preserve NOLOGIN, NOINHERIT, NOBYPASSRLS, SET-only membership, existing grants, and the actor-bound IT audit policy.
* Change no other Directory User column. Write one `user_disabled` domain audit per changed user with `actor_app_user_id`, keep `actor_user_id` null absent a genuine directory actor, and retain atomic success plus separate safe failure persistence.
* Keep responses and persisted snapshots free of raw emails, full rows, raw login/security events, SQL, QueryRun rows, permissions, session data, arbitrary JSON, and internal driver errors.
* Do not add frontend/navigation/UI, `disable_service_account`, additional actions, external notification delivery, queues, workers, schedulers, Redis, automatic retry/rollback, real LLM behavior, Supabase Auth, or M8 PR5+ work.

M8 PR4 delivered migration `0010_disable_inactive_user`; the exact action-role dependency reads and Directory User column UPDATE/RLS boundary; explicit `disable_inactive_user` registration; typed 90-day preview and snapshot validation; dependency-locked double revalidation with a stable execution-set invariant; active-human-to-disabled mutation only; actor-separated `user_disabled` domain audit; reused lifecycle audit/notifications/failure handling; and real PostgreSQL RLS, rollback, concurrency, nondisclosure, and migration-refusal coverage. Final verification passed 710 default backend tests with 150 expected PostgreSQL skips, all 860 disposable-PostgreSQL tests, 86 focused PostgreSQL action tests including the exact 20-case suite, fresh/round-trip/no-diff migrations, 188 frontend tests, TypeScript, and the production build. The final review was **Manual PR4 security and correctness review — not a CodeRabbit result**. No frontend, service-account action, additional action type, separate Execute endpoint, external delivery, queue/worker/scheduler/Redis, retry/rollback action, or M8 PR5 work was added. Preserve these boundaries through review and merge.

M8 PR5 may add only requester-facing Actions UX plus the two verified integration gaps on updated `main`: explicit action-suggestion metadata for the two approved action-aware templates and a requester-owned metadata-only action list endpoint.

M8 PR5 guardrails:

* Suggested actions must come only from explicit validated Domain Pack metadata and current successful non-truncated template results. Never infer action types from question text, generic columns, charts, free-query output, LLM output, or historic QueryRuns.
* Result-row UUID selectors are transient browser memory only. Do not persist them in QueryRun metadata, local/session storage, URL state, dashboard config, card layout, or another snapshot store.
* Reuse the generic preview/request/detail/cancel APIs, existing synchronous approval lifecycle, and shared `AccessibleOverlay`. Frontend permission checks are UX only; backend permissions, exact scopes, RLS, eligibility, revalidation, execution, audit, notifications, and concurrency remain authoritative.
* `GET /api/v1/actions` must enforce requester ownership in SQL, exclude abandoned drafts, use bounded pagination and validated status groups, and return only safe metadata plus requester-owned summary counts.
* User receives no action suggestion, CTA, navigation, or direct Actions route. Manager, Analyst, and Admin receive requester behavior only; Manager override/sensitive records remain summary-only in the UI.
* PR5 has no schema, migration, seed, permission, RLS, eligibility, execution, audit, notification-delivery, or failure-semantic changes.
* Do not add Approvals, Audit explorer, Notifications UI, approve/reject controls, a notification bell, external delivery, additional actions, a separate Execute endpoint, workers, queues, schedulers, Redis, automatic retry/rollback, real LLM behavior, Supabase Auth, or M8 PR6+ work.

M8 PR5 delivered explicit validated action metadata for the two approved templates; deterministic current-result suggestions; requester-owned metadata-only action listing; transient fail-closed browser selector resolution; the Suggested Action card and accessible Preview Drawer; requester Actions navigation, Home summary, tracking/detail/timeline, and cancellation; and permission, stale-response, responsive, accessibility, PostgreSQL, and release-blocking regressions. Final verification passed 739 default backend tests with 150 expected PostgreSQL skips, all 889 disposable-PostgreSQL backend tests, the exact 20-case suite, 222 frontend tests, TypeScript, the production build, Alembic no-diff verification, and manual role/desktop/mobile browser QA. The final review was **Manual PR5 requester UX review — not a CodeRabbit result**. PR5 is merged through PR #33. No schema/migration/seed/permission/RLS/eligibility/execution/audit/notification/failure change, Approvals/Audit/Notifications UI, approve/reject control, additional action, external delivery, queue/worker/scheduler/Redis, retry/rollback, or M8 PR6/PR7 work was added.

M8 PR6 may add only the human-facing Approvals, Audit, and Notifications UX plus exact authorized pagination/activity totals required by those screens and badges.

M8 PR6 guardrails:

* Reuse the existing approval, audit, notification, action-detail, permission, CSRF, and `AccessibleOverlay` contracts. Frontend permissions are UX only; backend authorization and current state remain authoritative.
* Pending approval totals must use the same dynamically authorized, exact-scope, self, threshold, override, and expiration decisions as the returned list. Notification and audit totals must use the same recipient/scope/filter predicates as their returned rows.
* Approve means synchronous Approve and Execute. Both approve and reject require a trimmed 1–1000-character reason, a current CSRF token, duplicate-submit prevention, and authoritative handling of completion, failure, expiration, races, policy escalation, and safe not-found.
* Analyst sees only backend-returned scoped audit fields. Admin-only before/after, self-approved, and failure-category fields render only when returned. Manager receives no Audit navigation or route under the current permission contract.
* Notifications remain database-only and current-recipient-only. Do not consume arbitrary stored payload fields, persist client notification state, add polling, or add external delivery.
* Shared activity counts remain in memory, reset across authenticated users, abort stale requests, and fail without inventing zero badges or breaking navigation.
* PR6 adds no migration, schema, seed, permission, role mapping, RLS, runtime-role, eligibility, revalidation, execution, lifecycle, audit-writing, recipient, QueryRun, or snapshot changes.
* Do not add a new frontend library, additional action, separate Execute endpoint, automatic retry/rollback, WebSocket, queue, worker, scheduler, Redis, email/Slack/push/SMS, Admin Users UI, Evaluation UI, real LLM behavior, Supabase Auth, or M8 PR7 work.

M8 PR6 delivered exact authorization-aware activity totals; typed abortable clients; permission-aware Approvals and Audit routes; responsive pending review and safe synchronous decision UX; scoped/global Audit browsing; current-recipient database notification access and mark-read controls; exact badges; and Analyst/Admin Home workflow summaries. Final verification passed 740 default backend tests with 150 expected PostgreSQL-only skips, all 890 disposable-PostgreSQL backend tests, the exact 20-case suite within 86 focused PostgreSQL action tests, 23 focused approval API tests, 247 frontend tests, TypeScript, the production build, fresh Alembic head/no-diff verification, desktop role-matrix plus 390px browser QA, and live isolated rejection/execution/Admin-override/self-approval workflows. The final **Manual PR6 correctness, scope, accessibility, and security-boundary review — not a CodeRabbit result** found and fixed 3 Minor issues, removed one unconsumed activity-state path, and left no actionable finding. Manager intentionally has no Audit UX because the current effective-permission contract does not grant it, despite a future-facing private-planning description. No schema/migration/seed/permission/RLS/execution/audit-writing/recipient behavior, external delivery, background infrastructure, Admin Users UI, Evaluation UI, or M8 PR7 work was added. Preserve these boundaries through review and merge.

M8 PR7 may add only release-hardening evidence and infrastructure: safe isolated E2E database preparation, the real Manager-to-Analyst governed workflow and negative User browser flows, the exact security requirement matrix, PostgreSQL/action/RLS CI release gates, narrowly required Admin Audit/export smoke, and defects directly exposed by those gates.

M8 PR7 guardrails:

* Do not change backend authorization, effective permissions, exact scopes, CSRF, RLS, runtime roles, action eligibility, revalidation, execution, lifecycle, audit-writing, notification recipients, or public API contracts unless a required release gate proves a current-contract defect and the fix is minimal.
* E2E preparation must be PostgreSQL-only, explicitly opted in, idempotent, local/CI endpoint validated, limited to a database name containing test/dev/e2e, and must refuse the configured normal application database and ambiguous endpoint overrides.
* The state-changing primary workflow must use a freshly migrated and seeded dedicated database and must not retry against mutated targets or depend on test order.
* Prefer mapping existing strong tests to requirements. Add only the narrowest missing release regression; do not duplicate test counts or refactor working PR1–PR6 code.
* PR7 adds no migration, schema, normal seed, permission catalog, role mapping, RLS policy, new action, separate Execute endpoint, retry/rollback action, queue/worker/scheduler/Redis/WebSocket, polling, external delivery, Admin Users UI, Evaluation UI, real LLM provider, Supabase Auth, or next-milestone work.
* Do not mark Milestone 8 complete until the exact 20-case suite, mapped PostgreSQL/security gates, full backend/frontend suites, primary and negative Playwright flows, migration/no-diff checks, accessibility/responsive checks, manual review, and resource cleanup all pass on the final committed HEAD.

M8 PR7 delivered guarded idempotent disposable E2E preparation; a no-retry Manager-to-exact-scope-Analyst reclaim workflow; a valid-CSRF User denial with persistence equality; Admin Audit/restricted-export smoke; the tracked exact 20- and broader 30-case security matrix; dedicated no-skip PostgreSQL and isolated primary-E2E CI jobs; and narrow missing RLS/dashboard/LLM evidence. The only product fix stops a terminal approval reload from making a requester-only Action detail request.

Final verification passed 14 E2E database-safety tests, the exact 20-case suite plus two concurrency cases, 756 default backend tests with 151 expected PostgreSQL-only skips, all 907 disposable-PostgreSQL backend tests with no skips, 247 frontend tests, both TypeScript checks, the production build, seven general Chromium flows, two isolated M8 flows, and a fresh PostgreSQL upgrade/current/no-diff check through migration 0010. The final **Manual M8 PR7 release review — not a CodeRabbit result** found and fixed 4 Minor issues with no Critical or Major finding and no remaining actionable issue.

No schema, migration, normal seed, permission, role mapping, RLS, runtime-role, action policy, lifecycle, execution, audit-writing, notification-recipient, or public API behavior changed. The intentional M8 limits remain: two V1 actions only, synchronous execution, database-only notifications, no automatic retry/rollback or background/external delivery, and operational intervention if execution and separate failure persistence both fail. Milestone 8 is complete and merged; M9 PR1 is active.

Milestone 2.5 introduced `access_scopes`, `user_access_scopes`, `data_resources`, `UserAccessContext`, `AccessDecision`, and `evaluate_access(subject, action, resource, context)`.

Milestone 3 added the security foundation for scope-aware PostgreSQL RLS before Query Engine work begins.

Milestone 3 delivered scope-aware PostgreSQL RLS, a `SET LOCAL` RLS context helper, DB session/helper integration for future Query Engine use, initial security/RLS tests, and policy helper refinements.

Milestone 4 implemented the backend Query Engine foundation on top of the existing Access Context Foundation and PostgreSQL RLS behavior.

Milestone 5 PR1 closed the remaining Milestone 4 backend Query Engine compliance gaps before frontend Ask Data UI began. That PR implemented:

* `POST /api/v1/queries/{query_run_id}/clarify`
* `GET /api/v1/queries/scope-history`
* `GET /api/v1/queries/department-history` as a V1 compatibility alias
* deterministic self-correction
* hardened safe query metadata for the future Ask Data UI

Milestone 5 PR5 added Ask Data role-gated SQL and Diagnostics tabs. Analyst/Admin can view generated/executed SQL in the SQL tab and safe technical diagnostics in the Diagnostics tab. User/Manager cannot view SQL tabs, Diagnostics tabs, generated SQL, executed SQL, or technical diagnostics. PR5 also added final Ask Data role matrix tests for User, Manager, Analyst, and Admin.

Milestone 5 PR6 added the Tailwind UI foundation, class-based light/dark mode, redesigned app shell/sidebar, redesigned Dashboard, focused Ask Data command workspace, light polish for remaining frontend pages, and final CSS/docs cleanup. PR6 did not change backend behavior, query execution behavior, auth/roles/RLS, dashboard card persistence behavior, CSV export behavior, action preview behavior, approvals, notifications, real LLM providers, API keys, Supabase Auth, Redis/background jobs, domain pack expansion, UI component libraries, or charting libraries.

Milestone 6 PR1 includes the dashboard catalog backend endpoint, my dashboard backend endpoint, dashboard creation backend endpoint, saving successful owned query runs as dashboard cards, safe metadata-only serializers, auth, CSRF, strict payload validation, dashboard visibility/manageability checks, and backend tests. It uses existing backend auth, CSRF, permission, and response conventions. Responses are metadata-only, do not execute saved cards, and do not expose SQL beyond existing `can_view_sql` API rules.

Milestone 6 PR2 added frontend dashboard/card API clients and types, read-only My Dashboard loading, personal dashboard creation UI, inline Ask Data Save as Card UI, and a safe read-only Dashboard Catalog UI. PR2 is complete and merged into `main`.

Milestone 6 PR3 — CSV Export Backend is complete and merged into `main`. It added controlled query-run and dashboard-card CSV export, export-time SQL validation, current-viewer PostgreSQL RLS, the dedicated read-only runtime role, CSV injection protection, safe filenames, successful export audit persistence, and PostgreSQL-backed export tests.

Milestone 6 PR4 — Card Refresh & CSV Export UI is complete and merged into `main`. It added frontend CSV downloads for successful Ask Data results and dashboard cards, secure dashboard-card refresh under the current viewer's `UserAccessContext`, automatic/manual refresh UI, safe table previews, and viewer-owned refresh `QueryRun` persistence without raw row snapshots.

Milestone 6 PR5 — Card Reordering & Layout Persistence persists card order through `DashboardCard.position` for owned personal dashboards only. It requires strict full-card-set validation, atomic updates, stale-layout conflict handling, dnd-kit pointer/keyboard ordering, explicit Move Up / Move Down controls, optimistic rollback, and refresh/export regression coverage. It must not expand `DashboardCard.layout` into a grid or resizing system.

The final Milestone 6 export policy adds `can_export_restricted_results` only to Admin through the deterministic permission catalog. Analyst still requires every referenced resource to be queryable and exportable. Admin restricted export requires both export permissions and may override only `is_exportable=false`; missing resources and `is_queryable=false` remain hard denials. Never hardcode the Admin role in export logic or bypass SQL validation, `queryops_query_runtime`, read-only execution, current-viewer RLS, row limits, CSV sanitization, ownership/visibility, or successful audit persistence. Restricted override usage must be audited without SQL or raw rows.

Milestone 4 delivered:

* Domain Pack Loader
* Query Templates API
* `LLMProvider` interface
* `MockLLMProvider`
* SQL generator wrapper
* Schema Context Builder
* SQL validator
* runtime RLS role hardening
* scoped read-only Query Executor
* internal Query Engine orchestration service
* Query Run API
* `QueryRun` persistence
* PostgreSQL/RLS query tests
* Query Engine security regression and deterministic MockLLM evaluation tests

Query Engine security rules:

* Backend authorization is the source of truth; frontend visibility is never enough.
* Query execution is read-only.
* SQL must be validated before execution.
* Execute only validator `sanitized_sql`, never raw user or provider output.
* Execution must use the dedicated non-owner read-only role `queryops_query_runtime`.
* Execution must use transaction-local PostgreSQL RLS context and PostgreSQL RLS.
* Non-queryable `DataResource` records are denied.
* `it_audit_events` is intentionally non-queryable in V1.
* Query Engine code must continue to use `UserAccessContext`, `DataResource`, `AccessDecision`, `evaluate_access(...)`, `authorize_resource_access(...)`, `RLSContext`, `build_rls_context(...)`, `set_rls_context(...)`, PostgreSQL RLS policies from `0005_scope_aware_rls.py`, and the existing `QueryRun` model.
* No real LLM calls, external provider integrations, or API-key requirements are allowed in Milestone 4.

M7 PR1 and M7 PR2 are complete and merged. M7 PR2's backend/frontend Home aggregate and dashboard-browser boundaries must be preserved. PR2 introduced no Alembic migration, database table, or schema change.

M7 PR1 implemented only:

* real URL routing for `/login`, `/`, `/ask`, `/profile`, and permission-gated `/admin/role-requests`
* My Dashboard as authenticated home
* a dark-first responsive shell with persistent light mode
* navigation containing only active capabilities
* Profile with the existing Role Upgrade flow for eligible non-Admin users
* transitional My Dashboard cleanup using existing dashboard APIs

M7 PR2 implemented only:

* `GET /api/v1/home/overview` with personal product metrics for every authenticated user
* scoped operational aggregates for effective scoped-data permissions and global aggregates for effective global-data permissions
* independent permission gating for `can_manage_users`, `can_approve_role_requests`, and `can_view_global_audit` Admin metrics
* `GET /api/v1/dashboards/library` with Owned/Shared classification and safe preview-card metadata
* `GET /api/v1/dashboards/{dashboard_id}` with safe ordered card metadata and safe not-found behavior
* role-aware Home, library search/filter/sort, accessible preview dialog, real `/dashboards/:dashboardId`, compact personal creation, and preserved M6 refresh/export/reorder compatibility

M7 PR2 security rules:

* Operational aggregates must use `UserAccessContext`, existing `DataResource` records, `evaluate_access(...)`/`authorize_resource_access(...)`, the non-owner read-only runtime role, `build_rls_context(...)`, `set_rls_context(...)`, and PostgreSQL RLS.
* Resource authorization is independent. Return null for a forbidden metric without revealing table or policy internals.
* Never join or associate `app_users` to `directory_users` by email, name, provider id, or inferred identity.
* User receives no operational domain metrics and no Admin metrics.
* Home, library, preview, and detail must not expose SQL, raw operational rows, raw card config, raw card layout, permission internals, owner email, or sensitive event detail.
* Preserve the existing `dashboard_is_visible` policy across catalog, library, detail, refresh, and export. Foreign personal and archived dashboards remain unavailable.
* Preserve existing current-viewer RLS refresh, controlled CSV export, and owned-personal full-card-set reorder behavior wherever those capabilities remain reachable.

Out of scope for M7 PR2 unless explicitly requested:

* card resizing
* x/y grid coordinates
* width or height persistence
* advanced `DashboardCard.layout` behavior
* database migrations, schema changes, new tables, or seed-policy expansion
* Recharts or any additional charting/component library
* charts, visualization rendering, card resizing, grid coordinates, or advanced layout behavior
* View/Edit editor, Add Card, card context menus, rename, duplicate, remove, or dashboard cloning
* department/global dashboard creation UI
* Ask Data redesign, templates consolidation, or five-query history drawer
* actions
* approvals
* notifications
* Users UI
* Audit UI
* real LLM/API-key support
* Supabase Auth
* domain pack expansion
* Full ABAC
* ReBAC
* masking
* policy builder UI
* dynamic policy engine
* tenant/project/region governance
* background jobs
* Redis
* API rate limiter

Do not show future or placeholder destinations in navigation. Templates, Role Upgrade as a standalone destination, Query History, SQL / Technical, Department Dashboards, Admin Console, Users, and Audit must remain absent from navigation in PR2. Frontend permission visibility is UX only; backend authorization remains the source of truth.

Use the term Scope in general product UI. Department remains valid in the IT Operations domain model, internal permission names, and V1 compatibility API names, but must not be presented as the product's universal governance concept.

Local `docs/planning/` documents may be updated for M7 PR3 because the user explicitly authorized it. They remain ignored and must never be staged or committed.

M7 PR3 is implementation-complete and owns only the full-dashboard editor, responsive versioned grid, visualization recommendation/rendering, safe dashboard/card actions, and Add Card flows described in `PROJECT_PLAN.md`. Retain the following rules through review and merge.

M7 PR3 guardrails:

* Every dashboard or card mutation must independently enforce backend dashboard manageability and effective permissions; frontend capability checks are UX only.
* Layout updates require dashboard/card row locks, a complete current card set, strict 12/6/1 breakpoint validation, no overlaps, approved size presets, optimistic `layout_version` concurrency, atomic commit, and safe conflict responses.
* `DashboardCard.layout` and `DashboardCard.config` may contain only the approved versioned layout and sanitized visualization shapes. Never accept or expose arbitrary config JSON.
* Never persist query-result rows in card config/layout, local storage, URL state, SavedQuery metadata, or another new snapshot store.
* SQL source requires effective `can_view_sql`, dashboard visibility, and a deterministic latest-successful linked QueryRun. Return only original question and stored sanitized/executed SQL.
* Refresh/export continue through the existing secure endpoints and must retain current-viewer `UserAccessContext`, SQL validation, validator-sanitized SQL, `queryops_query_runtime`, read-only execution, PostgreSQL RLS, row limits, CSV sanitization, and successful export audit persistence.
* Card removal deletes only the `DashboardCard`. Preserve `SavedQuery` and every `QueryRun`.
* Dashboard archive is soft deletion. Duplicates are new personal dashboards/cards that reuse SavedQuery references and never duplicate QueryRuns or raw rows.
* Keep the legacy order-only `PATCH /api/v1/dashboards/my/layout` contract compatible while the new versioned full-layout endpoint is added.
* Do not implement cross-dashboard card movement, shared-dashboard layout personalization, arbitrary freeform resize, custom chart colors/formulas, dashboard restore/sharing mutation, or department/global dashboard creation UI.
* PR3 itself did not redesign Ask Data or add the five-item history drawer; that work is complete in PR4.
* Do not add Actions, Approvals, Audit UI, Users UI, notifications, real LLM providers, Supabase Auth, Redis/background jobs, or Milestone 8 behavior.

M7 PR4 is implementation-complete. Follow `PROJECT_PLAN.md` for its delivered scope and completion evidence.

Agents working on PR4 must keep it frontend-only; preserve every existing backend, authorization, RLS, export, and dashboard security contract; never persist historic or current result rows outside QueryRun execution responses; and stop if an existing API is insufficient. Do not begin Milestone 8 work.

## 6. Product Direction

QueryOps AI is a governed conversational data workspace.

The product should eventually support:

* natural-language questions over structured data
* safe SQL generation
* SQL validation
* scoped database execution
* explained results
* saved cards and dashboards
* controlled operational actions
* approval workflows
* audit logs

The first domain is IT Operations, but the core system must remain generic.

IT Operations is a domain pack, not the whole product.

## 7. Architecture Decisions

Follow these locked decisions unless explicitly changed by the user:

* monorepo
* React + TypeScript + Vite frontend
* FastAPI + Python backend
* PostgreSQL database
* SQLAlchemy 2 and Alembic for database work
* Docker Compose for local development
* demo auth before real Supabase Auth
* Supabase Auth planned later for identity only
* QueryOps manages its own roles, departments, and permissions
* PostgreSQL RLS required in a later milestone
* LLM provider abstraction
* no direct LLM database mutations
* actions must be executed by deterministic backend logic
* actions require preview, policy check, approval, execution, and audit

## 8. Documentation Rules

Update `README.md` when:

* setup commands change
* Docker commands change
* backend run commands change
* frontend run commands change
* environment variables change
* repository structure changes
* verification commands change

Update `PROJECT_PLAN.md` only when the development plan or active milestone changes.

Keep `README.md` focused on the project.

Keep `PROJECT_PLAN.md` focused on implementation control.

Keep `AGENTS.md` focused on agent behavior rules.

## 9. Testing Rules

When adding backend code, add or update backend tests when practical.

When adding frontend code, add or update frontend tests when practical.

When adding database schema or seed behavior, add or update migration, seed, and relationship tests when practical.

Security-related behavior in later milestones must have tests.

Do not add complex E2E tests before the supporting app behavior exists.

Current verification commands:

Default backend suite:

```bash
cd backend
.venv/bin/pytest
```

PostgreSQL/RLS/Query Engine suite:

```bash
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/pytest tests/test_rls_postgres.py -q -rs
```

Alembic with local PostgreSQL:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+psycopg://queryops:queryops@localhost:5432/queryops .venv/bin/alembic check
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

## 10. Git Rules

Before starting work:

```bash
git status
```

Before finishing work:

```bash
git status
```

Only stage files related to the current task.

Do not stage ignored planning files.

## 11. Local Planning Files

Expected local planning files, if present:

```txt
docs/planning/01-product-brief.md
docs/planning/02-mvp-prd.md
docs/planning/03-technical-architecture.md
docs/planning/04-it-operations-domain-pack.md
docs/planning/05-security-permissions-matrix.md
docs/planning/06-actions-approvals-audit.md
docs/planning/07-api-contract.md
docs/planning/08-ui-flows-wireframes.md
docs/planning/09-evaluation-testing-plan.md
docs/planning/10-development-milestones.md
```

Use these files as context, but do not copy large private sections into committed files.
