# QueryOps V1 Manual QA

Use a freshly migrated and deterministically seeded disposable PostgreSQL database. Record date, tester, commit, browser, viewport, theme, and only safe controlled failure codes. Do not paste SQL, rows, prompts, provider payloads, keys, raw errors, or database URLs into the report.

Current result: **not performed**. This keeps V1 readiness `incomplete`.

## Roles and governed data access

- [ ] Log in as User, Manager, Analyst, and Admin.
- [ ] Confirm role-aware navigation and direct-route denials.
- [ ] Confirm User remains template-only and has no free-query or Action CTA.
- [ ] Confirm Manager can use scoped free query but cannot see SQL.
- [ ] Confirm Analyst can see only authorized SQL and technical details.
- [ ] Confirm Admin global behavior is clearly identified and remains policy-controlled.

## Query, dashboard, and export

- [ ] Run an approved Ask Data template.
- [ ] Run an authorized free query.
- [ ] Trigger and complete clarification without an SQL execution.
- [ ] Save a successful result as a Card.
- [ ] Open and refresh the saved Dashboard card.
- [ ] Export CSV and verify audit evidence and formula-injection sanitization.

## Actions, approvals, notifications, and audit

- [ ] Submit a Manager action request.
- [ ] Approve and execute as the exact-scope Analyst.
- [ ] Verify current-recipient Notifications.
- [ ] Verify the safe Action/Audit timeline.
- [ ] Verify expired and failed action states remain terminal and safe.
- [ ] Approve a role-upgrade request as Admin.

## Evaluation and readiness

- [ ] Confirm User cannot navigate to or directly open Evaluation.
- [ ] Confirm Manager sees only business-safe Evaluation and readiness fields.
- [ ] Confirm Analyst sees only the existing assigned-scope technical projection.
- [ ] Confirm Admin sees bounded global readiness gate values and safe usage totals.
- [ ] Confirm Ready, Not ready, and Incomplete include text labels and are not color-only.
- [ ] Confirm provider/model identity is not presented as a pass badge.
- [ ] Confirm Actions and Dashboards remain `not_measured` in the 40-case evaluation and point to deterministic release evidence.
- [ ] Confirm no run/rerun, API-key, provider/model selector, history, comparison, or arbitrary run picker exists.

## Accessibility, responsive behavior, and diagnostics

- [ ] Complete the flows in both light and dark themes.
- [ ] Complete the flows at a mobile viewport (390×844 or narrower equivalent).
- [ ] Verify keyboard navigation, visible focus, focus restoration, dialogs, drawers, tables, and status text.
- [ ] Confirm no browser console error, uncaught page error, or sensitive response detail appears.
