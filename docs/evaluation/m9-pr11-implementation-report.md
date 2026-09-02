# M9 PR11 — Evaluation V2 & Stability Release Gate

Implementation report dated 2026-09-02 (Asia/Jerusalem).

## Executive summary

M9 PR11 implementation is complete and locally validated. The branch is ready for push and deterministic GitHub CI, but Milestone 9 and QueryOps AI V1 remain incomplete because no qualifying live OpenAI evidence or complete manual QA has been accepted.

PR11 makes evaluation authoritative for the post-PR10 plan-only runtime. It adds a reviewed Evaluation V2 dataset, explicit semantic expectations, planner-quality measurements, plan-only failure stages, a fixed stability canary, a fail-closed three-run stability assessment, exact canary-to-full-run provenance matching, and a V2-aware readiness projection. It does not redesign Required/Suggested Intent, semantic grounding, deterministic SQL rendering, SQL safety, semantic conformance, authorization, PostgreSQL RLS, or the M8 Action Engine.

No OpenAI request was made. Mock remains the normal development and CI provider.

## Source state

- Branch: `feature/m9-evaluation-v2-stability-release-gate`
- Base `main`: `ec0c812ee6b651eb936a24f8e91c346baa9837d8` (PR #45 / M9 PR10 merge)
- Locally verified runtime checkpoint: `a12e4549c3cfe738ffffda70885dc1af92e26b09`
- Pre-report implementation HEAD: `bf0593a738cfbe416fb3c9e8cfabd41116a67d80`
- Readiness policy ID: `queryops-v1-readiness-v1` (unchanged)

## Checkpoint commits

| Commit | Checkpoint |
| --- | --- |
| `dbda88a` | Add Evaluation V2 semantic contract |
| `0ad1f68` | Add reviewed IT Operations Evaluation V2 dataset |
| `b2ab0c0` | Measure SemanticPlan quality and runtime failure stages |
| `0ccfabe` | Add curated V2 stability canary |
| `0092a50` | Require three-run canary stability evidence |
| `47ff506` | Gate V1 readiness on V2 stability evidence |
| `a4cf3ac` | Show V2 stability readiness in evaluation workspace |
| `bbc769c` | Align M9 evaluation docs with plan-only runtime |
| `a12e454` | Test current V2 evaluation through PostgreSQL API |
| `bf0593a` | Record PR11 deterministic release evidence |

## Evaluation V2 dataset

PR11 adds `it_operations_v2` version `2` with digest:

```text
a2ce20e766ee816a5fef357d8a46ef987ed3ba614f3b273f593bc63ed317e6b0
```

The set contains exactly 40 cases:

| Difficulty | Cases |
| --- | ---: |
| Easy | 10 |
| Medium | 15 |
| Hard | 10 |
| Security | 5 |

Answerability classification is 35 answerable, three denied, one unsafe, and one clarification. Semantic sources are recorded explicitly: 18 use the question plus catalog, 16 use catalog definitions, one is explicit-question-only, and five non-answerable cases are not applicable.

Historical V1 remains unchanged at `it_operations_v1` version `1`, digest:

```text
1e7b12fbf35de4d2c52937a762f3960df444eb3303ee7061a0e4506819c22bc4
```

The existing reviewed `itops-medium-009` baseline correction is preserved. No other frozen V1 case, baseline, template, threshold, or question was modified.

## Semantic contract

Each V2 case carries a strict, versioned semantic contract containing only justified binding expectations:

- answerability and semantic source;
- required catalog concepts, canonical metric, and composition rules;
- grain and output fields;
- aggregations, including distinctness;
- group-by fields;
- explicit HAVING predicates;
- result ordering.

The loader validates exact fields, bounded list sizes, safe identifiers, catalog references, entity columns, aggregation references, expected-outcome consistency, expected-table/column consistency, and the absence of result semantics on denied, unsafe, or clarification cases. The normal Domain Pack and historical V1 loader remain independent from V2 evaluation loading.

## Ambiguity review

All 40 V2 cases received a manual answerability and baseline-semantics review. Historical ambiguity was resolved only through an authoritative catalog definition, an explicit V2 rewrite, or clarification.

### Explicit rewrites

- `itops-easy-001`, `itops-medium-003`, and `itops-hard-001` replace generic “inactive” wording with the exact successful-login condition and 90-day window.
- `itops-easy-003`, `itops-easy-004`, `itops-medium-002`, `itops-medium-006`, `itops-medium-007`, `itops-medium-012`, and `itops-hard-003` make counts, distinctness, status sets, grouping, and required outputs explicit.
- `itops-medium-004`, `itops-medium-015`, `itops-hard-004`, `itops-hard-006`, `itops-hard-008`, and `itops-hard-009` replace hidden “recent”, “spike”, “reclaim opportunity”, and “most” semantics with exact windows, thresholds, measures, and ranking.
- `itops-medium-009` makes the distinct device grain explicit.
- `itops-hard-002` replaces the undefined “active device ownership” meaning with assigned devices.
- `itops-hard-007` ranks inactive human users by distinct assigned devices matching the existing non-compliant-device OR composition, using only inner-join, WHERE, grouped aggregation, and ordering semantics supported by the current V1 algebra.
- `itops-hard-010` ranks only departments that have both requested populations, using two explicit counts representable by existing inner joins and WHERE predicates.

### Catalog-defined meanings

Existing authoritative catalog concepts are used for non-compliant devices, active human users, active assignments, missing antivirus, disabled accounts, unsupported software, service accounts, unused paid licenses, exception assignments, terminated employees, stale devices, inactive licensed users, and high-risk software. No concept or grounding path was added merely to preserve a hidden baseline assumption.

### Clarification

`itops-security-005` — “Who is inactive?” — remains an explicit clarification case and carries no fabricated output semantics.

## Planner and runtime measurement

Evaluation now records safe, bounded planner observations for free-query success cases. New aggregate measurements include:

- eligible case count;
- generated and validated plan counts;
- SemanticPlan validation pass rate;
- Required Intent evaluated, passed, and adherence rate;
- renderer defect count;
- semantic-conformance defect count;
- semantic-contract evaluated, passed, and pass rate.

Per-case semantic scoring measures concepts, metric, composition rules, grain, outputs, aggregations, grouping, HAVING, and ordering without comparing generated SQL text or persisting raw rows.

Required Intent remains binding and fail-closed. Suggested Intent remains non-binding and cannot independently reject a valid SemanticPlan.

## Failure-stage taxonomy

The earlier provider-SQL-oriented generation classification is replaced with stages matching the plan-only runtime:

```text
grounding
plan_generation
plan_validation
sql_rendering
sql_safety
semantic_conformance
execution
result_comparison
setup
```

SQL-renderer and semantic-conformance failures are tracked as deterministic implementation defects, separate from ordinary provider or model-quality misses.

## Fixed V2 stability canary

The canary is `it_operations_v2_stability_canary` version `1`, digest:

```text
d07a3a67542d68af1828933d4519e1f9e2ece51b38571831b35883a1ff742e32
```

Its fixed case membership is:

| Case | Coverage |
| --- | --- |
| `itops-easy-005` | Canonical metric |
| `itops-easy-006` | Detail query |
| `itops-easy-008` | Deterministically compiled literal filtering |
| `itops-medium-006` | Grouped distinct count and multi-table chain |
| `itops-medium-009` | Free-query non-compliant-device OR composition |
| `itops-hard-004` | Explicit HAVING |
| `itops-hard-006` | Multi-table ranked aggregate |
| `itops-security-002` | Scoped authorization |
| `itops-security-003` | Unsafe request blocking |
| `itops-security-005` | Clarification |

The CLI supports explicit `--suite canary` selection. Canary selection cannot be combined with arbitrary filters, and the persisted suite identity includes its ID, version, digest, exact selected IDs, and coverage mapping.

## Three-run stability assessment

The stability gate deterministically selects the latest complete identity group and evaluates exactly its latest three runs. All three must match on:

- source Git SHA;
- provider and exact model;
- V2 dataset ID, version, and digest;
- semantic catalog identity and canonical hash;
- complete evaluation-environment identity;
- canary ID, version, digest, selected IDs, and count.

Every run must pass applicable thresholds, all security cases, persisted-shape validation, provider-measurement validation, and contain zero renderer or conformance defects. For each case, actual outcome, pass result, score, semantic-contract result, and failure stage must be stable across all three runs.

Zero, one, or two eligible runs are `incomplete`, and their valid matching run IDs are retained so the workspace can show 0/3, 1/3, or 2/3 without combining candidate identities. Malformed or mismatched evidence remains fail-closed. Outcome, result, semantic-contract, or failure-stage oscillation fails the stability gate. A failed canary cannot authorize a full release run.

## Readiness before and after PR11

Before PR11, readiness accepted one current unfiltered 40-case V1 OpenAI run plus deterministic gates and the existing quality thresholds.

After PR11, automated readiness requires:

1. a passed three-run V2 stability canary;
2. one complete unfiltered 40-case V2 OpenAI run;
3. exact candidate identity matching between the stable canary and full run;
4. the unchanged quality thresholds;
5. passed deterministic release gates;
6. planner implementation integrity;
7. zero renderer and semantic-conformance defects.

Automated readiness `ready` is necessary but does not complete the release. Milestone 9 and QueryOps AI V1 release completion separately require the complete manual QA checklist to pass on the same unchanged immutable candidate.

The readiness policy ID and thresholds remain unchanged:

- execution success rate at least `0.85`;
- result accuracy at least `0.75`;
- unsafe block rate exactly `1.00`;
- clarification accuracy at least `0.80`;
- security pass rate exactly `1.00`.

Filtered, partial, V1, Mock, stale, mismatched, malformed, or pre-PR11 runs cannot qualify as full V2 release evidence.

## API, CLI, and Evaluation workspace

- The current evaluation read service selects V2 evidence.
- The readiness API adds only a bounded `stability_canary` projection containing status, safe reason code, and run count.
- Readiness exposes nine ordered gates, including stability and planner implementation integrity.
- The CLI includes explicit suite selection and safe stability/readiness output without starting live evaluation implicitly.
- The Evaluation workspace shows the three-run stability status and `n/3` count using text and numbers, not color alone.
- No browser run/rerun, provider/model selector, API-key settings, history, comparison, or arbitrary run picker was added.

Manager, Analyst, and Admin projections remain server-controlled. User access remains forbidden. SQL, rows, prompts, provider payloads, baselines, raw errors, and hidden-scope evidence remain excluded.

## Runtime and security invariants

Final branch review confirmed:

- the provider remains plan-only;
- the deterministic SQL renderer is unchanged;
- PR8 Required/Suggested classification is unchanged;
- PR9 semantic grounding graph and ranking are unchanged;
- semantic catalog v3 is unchanged;
- SQL safety and semantic conformance are unchanged;
- authorization, runtime roles, and PostgreSQL RLS are unchanged;
- migrations and schema are unchanged;
- the M8 Action Engine, approval policy, audit, and notification behavior are unchanged;
- CI workflow configuration is unchanged;
- there is no LLM repair, second provider call, provider fallback, background execution, or live-provider CI.

The only Query Engine changes are allowlisted evaluation instrumentation: safe SemanticPlan observation fields, Required Intent validation status, and successful renderer status. They do not alter plan validation, SQL rendering, SQL execution, or authorization decisions.

## Deterministic verification

| Gate | Result |
| --- | --- |
| Backend without PostgreSQL | 1,284 passed; 156 expected PostgreSQL-only skips |
| Isolated PostgreSQL 16 backend | 1,420 passed; zero skips |
| Exact M8 release security suite | 20 passed; zero skips |
| Fresh migrations | Upgrade through `0010_disable_inactive_user` passed |
| Alembic current/check | Passed; no new upgrade operations |
| Frontend Vitest | 280 passed |
| General Playwright | 12 passed |
| M8 primary/negative Playwright | 2 passed |
| Ruff | Passed |
| Pyright | Zero errors and zero warnings |
| Compileall | Passed |
| ESLint | Passed |
| Application TypeScript | Passed |
| Node/Vite TypeScript | Passed |
| Production build | Passed |
| `git diff --check` | Passed |

The PostgreSQL gate used an isolated, task-owned PostgreSQL 16 container. The container and temporary backend/frontend processes were removed after verification. Existing user services and databases were not reset or removed.

## Review status

A complete manual branch diff review against `origin/main` found no remaining actionable issue. It specifically checked Query Engine behavior, Required/Suggested logic, grounding, the SQL renderer, SQL safety, semantic conformance, RLS, actions, migrations, provider contract, and accidental evaluation tuning.

CodeRabbit CLI `0.7.5` was installed but reported `not_authenticated`. Its browser authentication flow did not complete, so no CodeRabbit review result or zero-issue claim is made. Authentication can be completed later with `coderabbit auth login --agent` before running `coderabbit review --agent --base main`.

## Current release status and remaining work

It is not yet correct to claim `M9 COMPLETE` or `V1 READY`. The remaining release-evidence work is:

1. finish and review all PR11 fixes;
2. pass deterministic CI on the PR11 branch;
3. merge PR11;
4. pass deterministic CI on final `main`;
5. freeze that exact `main` SHA;
6. create a fresh deterministic Evaluation V2 environment manifest for that SHA;
7. obtain explicit authorization for the exact OpenAI model and maximum billable runs;
8. run the fixed V2 canary exactly three times;
9. require the stability assessment to pass;
10. run one matching full 40-case V2 evaluation;
11. require automated readiness to be `ready`;
12. complete the full role-based manual QA checklist on the same unchanged candidate;
13. only then mark Milestone 9 and QueryOps AI V1 release complete.

No live OpenAI call or complete manual QA was performed during implementation. Automated readiness currently remains `incomplete`, and release completion remains open.
