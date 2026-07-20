# M8 Release Security Test Matrix

This matrix is the tracked release contract for Milestone 8. Every row maps to
automated coverage. PostgreSQL rows run against an explicitly disposable local
or CI database; the M8 browser workflow runs in its own freshly migrated and
seeded database.

## Exact 20-case action workflow suite

The authoritative suite is `backend/tests/test_action_security_release.py`.
Case 14 in the broader workflow requirements is additionally covered by the
real concurrent approve/reject PostgreSQL test.

| # | Required behavior | Automated evidence |
|---:|---|---|
| 1 | User cannot create an Action Request | `test_action_security_01_user_cannot_create_action_request` |
| 2 | Manager can create but cannot approve | `test_action_security_02_manager_can_create_but_cannot_approve` |
| 3 | Analyst can approve an exact-scope request under 20 records | `test_action_security_03_analyst_can_approve_scoped_request_under_20` |
| 4 | Analyst cannot approve their own request | `test_action_security_04_analyst_cannot_approve_own_request` |
| 5 | Analyst cannot approve over 20 records | `test_action_security_05_analyst_cannot_approve_over_20_records` |
| 6 | Analyst cannot approve a policy override | `test_action_security_06_analyst_cannot_approve_policy_override` |
| 7 | Admin can approve a policy override | `test_action_security_07_admin_can_approve_policy_override` |
| 8 | Admin self-approval persists `self_approved=true` | `test_action_security_08_admin_self_approval_is_audited` |
| 9 | Expired preview cannot be submitted | `test_action_security_09_expired_preview_cannot_be_submitted_for_approval` |
| 10 | Expired pending approval cannot be approved | `test_action_security_10_expired_pending_approval_cannot_be_approved` |
| 11 | Revalidation skips records that are no longer eligible | `test_action_security_11_revalidation_skips_no_longer_eligible_record` |
| 12 | A newly required Admin override blocks non-Admin execution | `test_action_security_12_new_admin_override_blocks_non_admin_execution` |
| 13 | Concurrent/double approval executes at most once | `test_action_security_13_double_approve_does_not_execute_twice`; `test_concurrent_approve_requests_have_exactly_one_winner` |
| 14 | Concurrent approve/reject has one terminal winner | `test_concurrent_approve_and_reject_have_one_winner` |
| 15 | Database failure rolls back the success transaction | `test_action_security_14_transaction_rolls_back_on_database_failure` |
| 16 | Completed mutations write correlated application and domain audits | `test_action_security_15_completed_action_writes_app_audit_log`; `test_action_security_16_domain_change_writes_it_audit_event` |
| 17 | Public failure text does not leak internals | `test_action_security_17_user_safe_failure_does_not_leak_internals` |
| 18 | LLM/provider content cannot choose execution records | `test_action_security_18_llm_cannot_choose_execution_records` |
| 19 | Preview reads respect access context and PostgreSQL RLS | `test_action_security_19_preview_respects_rls_and_access_context` |
| 20 | Cross-scope action requires Admin | `test_action_security_20_cross_scope_action_requires_admin` |

CI runs the exact file in a named release-blocking step before running the rest
of the disposable-PostgreSQL backend suite.

## Required broader 30-case security matrix

| # | Required behavior | Automated evidence |
|---:|---|---|
| 1 | Manager cannot see `directory_users` outside department | `test_manager_cannot_see_another_department_rows` |
| 2 | Analyst cannot see devices outside department | `test_analyst_cannot_see_devices_outside_assigned_department` |
| 3 | Manager cannot see security-event details outside department | `test_finance_department_context_only_sees_finance_rows` |
| 4 | User cannot access a raw department directory list | `test_denied_context_fails_safe` |
| 5 | Admin can access authorized global domain data | `test_admin_global_query_returns_allowed_global_data` |
| 6 | User cannot view SQL | `test_user_can_run_approved_template_without_sql_visibility` |
| 7 | Manager cannot view SQL | `test_manager_template_response_hides_sql` |
| 8 | Analyst can view own SQL | `test_analyst_template_and_free_text_response_includes_sql` |
| 9 | Analyst cannot view another scope's query history/SQL | `test_analyst_can_retrieve_scope_query_history` |
| 10 | Admin can view authorized global query history and SQL | `test_admin_can_retrieve_global_scope_query_history`; `test_admin_response_includes_sql` |
| 11 | User cannot run free query | `test_user_without_free_query_permission_is_denied` |
| 12 | Manager free query is department scoped | `test_manager_scoped_template_query_returns_only_assigned_department_rows` |
| 13 | Analyst free query is department scoped | `test_analyst_scoped_free_text_query_works_for_assigned_it_scope` |
| 14 | Admin free query can be global | `test_admin_global_template_query_returns_allowed_global_data` |
| 15 | Ambiguous/unsupported query triggers safe clarification | `test_unsupported_free_text_returns_safe_clarification_and_persists` |
| 16 | Raw emails are not sent in LLM schema context | `test_context_contains_no_row_data_or_internal_policy_details` |
| 17 | Raw security-event descriptions are not sent in LLM schema context | `test_context_contains_no_row_data_or_internal_policy_details` |
| 18 | Governed aggregate-safe resources may be sent as schema context | `test_manager_context_includes_allowed_queryable_scoped_resources` |
| 19 | Approval reasons are not sent in LLM schema context | `test_context_contains_no_row_data_or_internal_policy_details` |
| 20 | `app_audit_logs` entries are excluded from LLM schema context | `test_context_excludes_tables_outside_domain_pack_and_product_tables` |
| 21 | Card refresh runs under current viewer context | `test_card_refresh_uses_viewer_context_instead_of_creator_context` |
| 22 | User cannot view foreign/private sensitive dashboard data | `test_dashboard_detail_enforces_personal_scope_archive_and_safe_not_found`; `test_postgres_foreign_personal_dashboard_returns_safe_not_found` |
| 23 | Manager receives only safe scoped dashboard metadata | `test_postgres_library_and_detail_preserve_dashboard_visibility_and_safe_shape` |
| 24 | Analyst can view exact-department dashboard details | `test_dashboard_detail_allows_analyst_exact_scope_and_admin_global_scope[demo.analyst@queryops.local-department-IT-IT]` |
| 25 | Admin can view global dashboard details | `test_dashboard_detail_allows_analyst_exact_scope_and_admin_global_scope[demo.admin@queryops.local-global-None-Global]` |
| 26 | User cannot create an Action Request | Action case 1 |
| 27 | Manager can create but cannot approve | Action case 2 |
| 28 | Analyst cannot approve their own request | Action case 4 |
| 29 | Analyst cannot approve over 20 records | Action case 5 |
| 30 | Policy override requires Admin | Action cases 6 and 7 |

## Additional release gates

- Query/export runtime role, read-only transactions, RLS, restricted-export
  policy, and audit: `test_query_runtime_role_postgres.py`,
  `test_exports_postgres.py`, and `test_card_refresh_postgres.py`.
- SQL injection and unsafe provider output: `test_sql_validator.py` and
  `test_query_engine_security_regression.py`.
- CSV formula injection: `test_exports_api.py` CSV sanitization cases.
- Role-aware frontend rendering: frontend unit tests plus the general Chromium
  E2E suite.
- Full governed workflow, synchronous approve-and-execute, exact badges,
  responsive routes, real logout/user switching, and User valid-CSRF denial
  with before/after persistence equality: `frontend/e2e/m8-workflow.spec.ts`.
- Admin Audit plus restricted-export smoke: `frontend/e2e/ask-data.spec.ts`.
