# QueryOps AI — Development History

This document preserves useful implementation history for archaeology. It does not authorize new work and is not a source of current project status. See [`PROJECT_PLAN.md`](../../PROJECT_PLAN.md) for the active objective and [`AGENTS.md`](../../AGENTS.md) for permanent repository rules.

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
