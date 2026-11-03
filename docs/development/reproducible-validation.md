# Reproducible local synthetic validation (M10 W8)

From a **clean, committed checkout**, with local Docker running, Git and host
Python 3.12+, run at repository root:

```bash
python3.12 scripts/validate_local.py --evidence /tmp/queryops-validation-evidence-001
```

Use a new evidence directory outside the checkout on every run. The entry point
builds from `git archive HEAD`, installs backend dependencies and `npm ci`, installs
Playwright Chromium/system dependencies, and runs the deterministic CI graph.
No local Python virtualenv, Node installation, `.env`, running application, database,
or pre-existing dependency installation is used. Initial image/package downloads
need network access and sufficient Docker disk/RAM; execution containers have no
external network. Allow several minutes, especially for the first build.

## Relationship to CI

The six jobs in [CI](../../.github/workflows/ci.yml) remain authoritative.
The adapter reads their run commands using the already locked `js-yaml` dependency
from ESLint, and rejects changed gate IDs, aggregate dependencies or selected step
names until the adapter is updated. CI workflow changes still need adapter review:
this is a small explicit adapter, not a general GitHub Actions emulator.

| Existing gate | Local execution |
| --- | --- |
| Backend | Ruff, explicit Pyright boundary, compileall, default pytest with counted PostgreSQL skips; supported backend Dockerfile auth smoke and Compose configuration boundary checks |
| PostgreSQL Security | New PostgreSQL 16 cluster; new explicitly disposable security DB; Alembic upgrade/current/check; exact 20 action cases; complete remaining backend suite; existing module-selection/zero-skip assertions, plus persisted scoped Evaluation selection |
| Frontend | Locked npm installation; ESLint, both TypeScript checks, Vitest, build |
| E2E | Separate new cluster/DB, migrations and synthetic seed; actual backend/frontend, general Chromium flows excluding `@m8-primary` |
| M8 Primary E2E | Separate new cluster/DB; existing migration/seed/preparation command; six sequential spec files from CI, including all real PostgreSQL scoped Evaluation API/browser cases without route mocks |
| V1 Deterministic Release Gates | Success only after every preceding job succeeds; any failure stops the local run and leaves remaining coverage incomplete |

Local differences: Linux containers run on the Docker engine's architecture
(for example ARM64 on Apple Silicon), while GitHub uses Ubuntu hosted runners.
Backend Python 3.12 and Node 22 match CI major versions. The supported backend
Dockerfile is built and its auth smoke runs offline; Compose configuration is
validated but the interactive Compose stack is not started. Tests are copied from
the committed tree into that smoke container instead of using the development
bind mount. Browser servers are directly supervised in the runner's isolated
network namespace. GitHub-specific checkout/setup/upload/concurrency steps are not
emulated. No CI architecture or product contracts change.

## Isolation and lifecycle

- There is **no database URL, existing-container or existing-volume input**. The
  host forwards only PATH, HOME, TMPDIR and DOCKER_CONFIG to Docker/Git. Application,
  provider, PostgreSQL, proxy, Compose and Docker endpoint environment overrides
  are discarded. A local Unix-socket Docker context is required.
- Every run has an unpredictable UUID namespace. Names are checked before creation;
  conflicts fail instead of adopting resources. Only committed files enter build
  contexts, excluding ignored local credentials and data.
- PostgreSQL uses a private network namespace and tmpfs data. Nothing publishes a
  host port, binds a host source/data directory, mounts a user volume or mounts the
  Docker socket. Browser/servers share the new PostgreSQL container's loopback
  namespace, so API and frontend both use `127.0.0.1` consistently. Vite uses
  `--strictPort`; no existing application is reused.
- A **fresh cluster per database gate** isolates cluster-global roles. Existing
  migration role protections are preserved; databases are created with CREATE
  DATABASE and never dropped/replaced/adopted. Existing preparation/test guards
  still receive explicitly disposable test/e2e URLs distinct from DATABASE_URL.
- Backend/frontend runtime uses explicit `AUTH_MODE=demo`, `LLM_PROVIDER=mock` and
  synthetic session settings. No host API key enters a container. No route starts
  live provider experiments; runtime network isolation also blocks external calls.
- Normal exit, failure, SIGINT and SIGTERM remove only registered containers after
  rechecking the run label, using immutable container IDs, and remove only labeled
  run images. Container-owned anonymous volumes are removed with their container;
  no volume/network pruning or Compose down command runs. Cleanup errors make the
  result fail and retain resource identity in the summary.
- Docker base images and build cache remain reusable. They are not user data and
  are never globally pruned. SIGKILL, host/daemon failure or power loss cannot run
  Python cleanup. Use the summary's run label to inspect leftover resources, then
  explicitly verify ownership before manually removing them; never use global prune.

The adversarial host check uses only its own temporary synthetic protected cluster
and volume. It checks byte-identical inspection plus database/role/sentinel content
after conflict rejection, partial creation, process failure and refused foreign-owner
cleanup. It requires Docker and fails rather than skipping:

```bash
python3.12 scripts/validation/test_lifecycle.py
```

Focused unit regressions run automatically in both backend CI selections:

```bash
cd backend
.venv/bin/pytest tests/test_local_validation.py -q
```

## Evidence and limits

`summary.json` records source SHA, unique run ID, Docker/image identities, gate
outcomes and cleanup. Per-gate JSON records Python/Node/npm and installed backend
versions, frontend dependency versions and lock hash, PostgreSQL server version,
Alembic revision, completed commands and executed/pass/fail/skip counts. Only JSON
summaries leave execution containers; raw test output, credentials, SQL, persisted
rows, browser traces/screenshots and exception bodies do not. Failure reports name
the active fixed CI step and exception type; a setup failure may have no suite counts.
This intentionally limits diagnostics. Reproduce using the same source SHA for a
closer inspection inside a separately owned disposable environment.

`/health` is process liveness only. Browser startup additionally requires frontend
HTTP, real seeded demo login, authenticated `/auth/me` and template API success.
The browser suites then exercise persistence and application behavior. A green
local result establishes deterministic local synthetic evidence, **not production
readiness, actual provider quality or V1 release qualification**.

Backend dependencies use the existing bounded version ranges rather than a full
lock; Docker tags and downloaded browser/system packages can change. Image IDs,
installed versions and frontend lock hash identify what actually ran, not a promise
of bit-for-bit rebuilds. Existing fixtures use current UTC reference times and some
browser preparations re-anchor synthetic time; no frozen Evaluation data or historic
evidence is changed. Full manual QA, authorized matching live quality evidence,
freeze and final V1 completion remain W9 work requiring separate authorization.
