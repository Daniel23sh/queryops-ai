# QueryOps AI — Risk-Based Validation Model

Use the lowest level that covers the change's real blast radius. Level is determined by affected boundaries, failure impact, and reversibility—not diff size. Validation below is a minimum; failures, uncertainty, or broader discovered impact require escalation.

Release validation remains governed by [`docs/evaluation/v1-quality-gates.md`](../evaluation/v1-quality-gates.md) and the aggregate CI job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). This model does not weaken those gates.

## 1. Classification Rules

Classify by the highest-risk behavior touched:

- **V0 — Local / trivial:** isolated documentation, copy, styling, test-only, or pure mechanical changes with no behavior/security contract impact.
- **V1 — Normal:** bounded application behavior with a clear local contract and focused tests; no PostgreSQL-specific semantics or security boundary changes.
- **V2 — Cross-system / high-risk:** multiple layers, API/persistence contracts, authorization-sensitive reads, database-backed behavior, or user-visible integration flows.
- **V3 — Critical / release:** permissions, RLS, roles/grants, runtime roles, migrations, state-changing/destructive workflows, concurrency/locking, LLM/SQL trust boundaries, evaluation readiness, release policy, or similarly broad/irreversible behavior.

Escalate one or more levels when the change crosses an additional boundary, lacks focused regression coverage, changes a public/persisted contract, depends on database behavior not represented by lightweight tests, exposes sensitive data, or produces unexplained failures. When uncertain between two levels, use the higher one.

## 2. V0–V3 Matrix

| Level | Typical examples | Minimum expected validation | PostgreSQL / integration / migrations | Review |
| --- | --- | --- | --- | --- |
| **V0** | Documentation wording; isolated CSS/copy; mechanical test cleanup; pure local refactor with unchanged contract | Inspect the focused diff; run the narrowest relevant test or syntax/static check when executable behavior changed; always run `git diff --check` | PostgreSQL, browser, and migration checks are not expected. If correctness depends on them, this is not V0. | Author self-review |
| **V1** | Ordinary component fix; bounded API validation bug; pure Query Engine helper change; frontend state or rendering change | Focused affected tests plus relevant language checks. Add nearby regression coverage for changed behavior. Do not require the full backend suite by default. | PostgreSQL only when the behavior actually depends on PostgreSQL—in which case classify at least V2. Browser testing is expected only for a material user flow not adequately covered by component tests. Migration checks are not expected. | Author self-review; independent review optional |
| **V2** | Coordinated frontend/API change; response-schema or persistence change; dashboard/export flow; authorization-sensitive read path; database-backed feature | Focused tests across every affected layer, relevant Ruff/Pyright or lint/type checks, and broader regression tests around the changed subsystem | PostgreSQL-backed tests are mandatory for DB semantics, persistence, authorization/RLS reads, transactions, or locking. Browser testing is expected for changed cross-layer user flows. Run Alembic `upgrade/current/check` when models, metadata, schema assumptions, or migrations are affected. | Independent review for complex, security-adjacent, concurrency-sensitive, or high-blast-radius V2 work |
| **V3** | Permission/RLS/grant/runtime-role change; migration; action execution; destructive/state-changing path; SQL safety/provider trust boundary; readiness/release logic; release candidate | Full CI-equivalent deterministic gates plus focused adversarial/regression evidence for the changed boundary | Isolated disposable PostgreSQL with no relevant skips is mandatory. Migration/no-diff checks are mandatory; test upgrade/downgrade behavior when a migration changes. Run relevant general browser flows and the isolated state-changing M8 flow when its contracts are affected. Actual releases must pass the authoritative release gates. | Independent review required, in addition to author self-review |

## 3. Commands That Exist Today

Run commands from the shown directory. `.venv/bin/...` matches the checked-in development workflow when the local backend environment exists; CI uses the equivalent installed commands directly.

### Backend: focused and static

```bash
cd backend
.venv/bin/pytest tests/<test_file>.py -q
.venv/bin/pytest tests/<test_file>.py::<test_name> -q
.venv/bin/ruff check <changed_python_paths>
.venv/bin/python -m compileall -q app scripts
.venv/bin/pyright
```

`pyright` checks the explicit include set in [`backend/pyproject.toml`](../../backend/pyproject.toml); it is not a whole-backend type check.

Backend CI-equivalent non-PostgreSQL gate:

```bash
cd backend
.venv/bin/ruff check app scripts
.venv/bin/pyright
.venv/bin/python -m compileall -q app scripts
.venv/bin/pytest
```

### Frontend: focused and full

Scripts are defined in [`frontend/package.json`](../../frontend/package.json).

```bash
cd frontend
npm test -- src/<affected_test>.test.tsx
npx eslint src/<changed_file>.tsx
npm run lint
npm run typecheck:app
npm run typecheck:node
npm test
npm run build
```

Use a focused Vitest file for V0/V1 where sufficient. Run the relevant type check for changed TypeScript contracts; use the full lint/test/build sequence for broad V2 and V3 frontend changes.

### PostgreSQL and migrations

Use a separate local database whose name contains `test`, `dev`, or `e2e`, and explicitly opt in to destructive tests. Never point these variables at the normal application database.

The checked-in [Docker Compose stack](../../docker-compose.yml) can start PostgreSQL; with its default credentials, a disposable database can be created explicitly:

```bash
docker compose up -d postgres
docker compose exec postgres createdb -U queryops queryops_validation_test
```

```bash
cd backend
export DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:<port>/<application_db>
export POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:<port>/<disposable_test_db>
export POSTGRES_TEST_DATABASE_DISPOSABLE=1

DATABASE_URL="$POSTGRES_TEST_DATABASE_URL" .venv/bin/alembic upgrade head
DATABASE_URL="$POSTGRES_TEST_DATABASE_URL" .venv/bin/alembic current
DATABASE_URL="$POSTGRES_TEST_DATABASE_URL" .venv/bin/alembic check
.venv/bin/pytest tests/<relevant_postgres_test>.py -q -rs
```

For V3 PostgreSQL validation, reproduce the two CI selections and treat any relevant skip as missing evidence:

```bash
cd backend
.venv/bin/pytest tests/test_action_security_release.py -q -rs
.venv/bin/pytest --ignore=tests/test_action_security_release.py -q -rs
```

The authoritative isolated-database creation, migration, and zero-skip assertions are in the `PostgreSQL Security` job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml). The action cases are mapped in [`docs/security/m8-release-test-matrix.md`](../security/m8-release-test-matrix.md).

### Browser and cross-layer flows

Playwright configuration is in [`frontend/playwright.config.ts`](../../frontend/playwright.config.ts).

```bash
cd frontend
npm run test:e2e -- e2e/<flow>.spec.ts --project=chromium
npx playwright test --grep-invert @m8-primary
```

General flows require a migrated, seeded PostgreSQL-backed app. The `@m8-primary` flow is intentionally excluded because it mutates state and requires its own disposable database. Its existing preparation and execution commands are:

```bash
cd backend
.venv/bin/python scripts/prepare_m8_e2e.py

cd ../frontend
npx playwright test e2e/m8-workflow.spec.ts --project=chromium
```

These commands require the guarded `M8_E2E_DATABASE_URL` and `M8_E2E_DATABASE_DISPOSABLE=1` environment plus separately running backend/frontend services. Follow the `M8 Primary E2E` CI job rather than improvising against a normal database.

### Readiness and release

The existing readiness check is read-only and evaluates one persisted run:

```bash
cd backend
.venv/bin/python scripts/check_v1_readiness.py --run-id <evaluation_run_uuid>
```

It does not replace deterministic CI, qualifying live evidence, or manual QA. Real-provider execution remains separately authorized and governed by the tracked quality-gate procedure.

## 4. Boundary Rules

- **PostgreSQL:** Mandatory whenever correctness depends on roles, grants, RLS, transaction-local context, PostgreSQL SQL behavior, locks, concurrency, or database-enforced constraints. A passing lightweight/default suite with PostgreSQL tests skipped is not sufficient.
- **Security:** Exercise both allowed and denied behavior, safe failure/disclosure, exact scope, and persistence equality or rollback where relevant. V3 also requires the authoritative mapped security suites affected by the change.
- **Migrations:** Run `alembic upgrade head`, `alembic current`, and `alembic check` against a fresh disposable PostgreSQL database. For a changed migration, also verify its intended predecessor-to-head path and downgrade/upgrade round trip when downgrade is supported.
- **Browser:** Use component tests for local presentation logic. Add Playwright when routing, authentication/session behavior, role-aware visibility, cross-layer requests, responsive interaction, or a governed end-to-end workflow materially changes.
- **CI:** Do not weaken or bypass existing jobs. Passing CI is required where repository policy requires it, but focused local evidence should still target the changed risk before CI.

## 5. Independent Review Policy

Independent review means a fresh-context agent, qualified human, or configured review tool examines the final diff and validation evidence for correctness, regressions, security boundaries, failure modes, and missing tests.

- V0/V1: not required unless the change proves more complex than classified.
- V2: required only for genuinely complex, security-adjacent, concurrency-sensitive, or high-blast-radius changes.
- V3: required. If unavailable, report that evidence gap rather than describing author self-review as independent.

Review findings that expand the affected boundary require reclassification and corresponding validation.

## 6. How an Agent Chooses a Level

1. List the contracts and layers the change can affect.
2. Start at the highest matching example in the matrix.
3. Raise the level for security sensitivity, PostgreSQL-specific behavior, irreversible state, unclear coverage, or broad downstream consumers.
4. Select focused commands first, then add the level's mandatory database, browser, migration, and review evidence.
5. Record what ran, what did not, and why. Never claim PostgreSQL, browser, independent-review, or release evidence from a lighter substitute.

## 7. Current Tooling Gaps

- No single local command reproduces the complete CI validation graph.
- No repository script creates, migrates, tests, asserts zero skips, and cleans up a disposable PostgreSQL validation database end to end.
- No single local command orchestrates the isolated backend/frontend services and guarded `@m8-primary` browser flow; CI is the canonical recipe.
- Pyright covers an explicit high-risk include set rather than the entire backend.
- There is no checked-in Markdown lint or link-validation command.
