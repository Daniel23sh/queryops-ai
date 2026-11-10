# Planner reliability study

This exploratory diagnostic compares `gpt-6.1-terra` reasoning `low` and `medium`.
Preparation, deterministic tests and CI remain offline. V1 remains unqualified after the first W9
canary. PR #78 corrected a separate temporal Suggested Intent defect. Both arms
include that correction, so the study cannot estimate its effect on W9.

## Preregistration

The [fixture specification](../../backend/scripts/planner_study_fixtures.py) fixes
all eight questions, accepted structured plans, expected row multisets and
witnesses. The sources are the IT Operations catalog, its field and relationship
definitions, and the [independent ownership fixtures](../../backend/scripts/semantic_ownership_fixtures.py).
The overlap review uses frozen qualification and W6c question text for exclusion.
It does not use their oracles. No expected plans or witness rows enter the request.
Score slot observations without the arm label.

| Slots | Expected semantics and distinguishing witnesses |
| --- | --- |
| Composition | Both ask for laptop hostnames. The posture policy includes status-only, antivirus-only and encryption-only lapses. The recorded-status request uses that field alone. A healthy laptop, qualifying desktop and hidden laptop guard against extra rows. |
| Grain | Count managed devices per declared device type. Count distribution groups with members at group grain. One populated group has two members, another has none, and a security group has a member. Row count and wrong group type fail. |
| Clarification | “Urgent” has no priority definition in the catalog. Require structured `ambiguous_question` with no SQL. The explicit critical-priority control requires a scalar count. A high-priority ticket distinguishes the readings. The wire schema supplies only a reason code, so specificity beyond that code is unmeasured. |
| Relationships | Both ask about outdated antivirus. The same device belongs to IT and its assignee belongs to Finance. An otherwise similar device is outside both assigned scopes and a visible device with missing antivirus distinguishes the filter. |

The existing joined-row Suggested Intent fallback is unchanged. The
`grain-memberships` fixture is flagged before comparison. Report its two results
per arm separately. A valid `COUNT(*)` on memberships is an interpretation miss
on the fixture, with cause ambiguous between the hint and model interpretation.
It cannot contribute a repeatable unflagged gain. On the device and ticket
single-table counts the equivalent explicit non-null key forms are accepted.
The scorer accepts listed concept/literal equivalents, independent aggregation
labels, and column or row order changes with the same multiset. It checks exact
relationship roles, selected composition and effective predicates.

The two execution blocks each pair the arms on every prompt. Four pairs begin
with each arm in block one. All eight arm orders reverse in block two. Each
slot is fresh. The two bodies for a prompt differ only in reasoning effort.
Actor, exact assigned scopes, projected candidates, instructions, schema, source,
dependencies and database contents are fingerprinted. The synthetic UTC
reference is fixed because none of the fixtures uses relative time.

## Offline reproduction

Use a fresh dedicated PostgreSQL 16 cluster with a random loopback port and
password. The connection user owns the empty study database. Use a private
operator directory outside the checkout. Example from `backend/`, with Docker
and the existing backend virtual environment available:

```bash
umask 077
study=$(mktemp -d "${TMPDIR:-/tmp}/queryops-planner-study.XXXXXXXX")
study=$(cd "$study" && pwd -P)
label=$(basename "$study")
db=planner_study_test_$(openssl rand -hex 8)
password=$(openssl rand -hex 24)
openssl rand -hex 16 > "$study/owner"
docker run -d --label "queryops.study.owner=$label" --name "$label" \
  -e POSTGRES_USER=queryops -e POSTGRES_DB="$db" -e POSTGRES_PASSWORD="$password" \
  -p 127.0.0.1::5432 postgres:16.14 > "$study/container"
cid=$(cat "$study/container")
test "$(docker inspect -f '{{index .Config.Labels "queryops.study.owner"}}' "$cid")" = "$label"
# Wait until this container's PostgreSQL accepts TCP connections.
docker exec "$cid" pg_isready -h 127.0.0.1 -U queryops -d "$db"
port=$(docker port "$cid" 5432/tcp | cut -d: -f2)
export PLANNER_STUDY_DATABASE_URL="postgresql+psycopg://queryops:$password@127.0.0.1:$port/$db"
printf "COMMENT ON DATABASE %s IS 'queryops-planner-study:%s';\n" "$db" "$(cat "$study/owner")" |
  docker exec -i "$cid" psql -v ON_ERROR_STOP=1 -U queryops -d "$db"
DATABASE_URL="$PLANNER_STUDY_DATABASE_URL" QUERYOPS_APP_DATABASE_ROLE=queryops .venv/bin/alembic upgrade head
DATABASE_URL="$PLANNER_STUDY_DATABASE_URL" .venv/bin/alembic check
.venv/bin/python -m scripts.planner_study initialize --owner-receipt "$study/owner"
.venv/bin/python -m scripts.planner_study manifest --owner-receipt "$study/owner" --manifest "$study/manifest.json"
.venv/bin/python -m scripts.planner_study dry-run --owner-receipt "$study/owner" --manifest "$study/manifest.json" --evidence "$study/dry-run"
```

Check the captured container ID and owner label before any eventual cleanup.
Keep the database and role configuration unchanged between manifest and dry-run.
The harness accepts only the expected PostgreSQL driver, loopback endpoint,
database name, owner receipt, and migration head. Initialization refuses a
nonempty database. The dry-run SDK receives an in-process mock transport and a
non-secret placeholder. The diagnostic ledger claims a fresh directory before
use and commits every reservation before generation. A pending slot or write
failure prevents progression. It retains only bounded result stages and usage.

## Decision and future authorization

Advance medium for separate qualification consideration only at 14/16 or
better with at least three net paired gains, positive net gains in both blocks,
and repeatable improvement on at least two unflagged prompts across two
families. A repeatable improvement means medium passes both blocks and low
misses at least one. Medium must pass both clarification controls in both blocks.
Security, renderer and conformance defects invalidate advancement. A comparable
study also requires complete usage and latency. Proposed tolerances are medium
median provider duration and uncached-equivalent token cost each at most twice
low. Retain low if a valid comparison misses the bar. No study outcome qualifies
either profile for release.

## Activation engineering and live approval

The activation implementation is study-only. It keeps the preregistered request
bodies and scoring. Both study profiles now disable SDK and transport retries
and redirects. The official Responses endpoint, verified TLS, 45-second timeout,
`store=false` and 2,048 output tokens per response are fixed. The ceiling is 32
logical slots, 32 physical forwards and 65,536 output tokens across 32 responses.
A physical forward is entry into the underlying transport. Its presence cannot
prove receipt or billing, and a timeout can leave both unknown. Input byte counts
in the new manifest inform updated token and cost estimates. Estimates and
telemetry do not cap the bill.

After the activation PR merges, the owner must complete these steps before any
live grant:

1. Choose one dedicated Linux host with a stable OS machine ID, ext4 or XFS
   local storage with durable sync, and a dedicated non-root runner UID/GID with
   no login, unrelated processes, shared privileges or existing credentials.
   Native macOS and unsupported storage fail closed. Protect the host from
   rollback, snapshots restored in place, and a second eligible launch host.
   A root operator controls the host, state and OpenAI credential.
2. Install the reviewed standard-library launcher from the final merge in an
   administrator-controlled location. Use a full clean checkout of that exact
   merged `main` with a verified matching `origin/main`. Use a separate venv
   created with `--copies`, with the approved dependency versions and no
   editable packages. Both trees and all ancestors must be root-owned and
   immutable to the runner. Prepare with an isolated interpreter and bytecode
   writes disabled. Keep generated files, credentials and evidence out of the
   live checkout. Verify the installed OS Python, launcher, checkout and venv.
3. Prepare a fresh dedicated PostgreSQL 16 cluster using the offline procedure.
   Keep it quiescent and isolated from other writers for the full window. Verify
   the exact candidate's migrations, synthetic ownership receipt, manifest and
   dry run. Keep the database and policies unchanged. Use separate synthetic
   PostgreSQL resources from the W9 environment and terminal W6c journals.
4. Provision the single root-owned, runner-readable state directory
   `/var/lib/queryops/queryops-planner-study-v1` on the approved host. Do not
   create or replace its `claimed` entry. Place the regenerated `manifest.json`,
   `database-url` and `database-owner` in the root as root-owned mode 0600
   regular files. Verify the machine ID digest and root device/inode for approval.
5. Separately authorize the final merged source and manifest digest, both
   effective profile fingerprints, all request hashes, the full ordered named
   schedule and its digest, the official endpoint, requested and expected
   returned model, project ID, credential version and exact credential identity,
   host, state device/inode and runner IDs. Bind a UTC start and expiry
   (whole seconds, `Z` suffix), 32-slot and 32-forward caps, token limits,
   refreshed input and cost estimates, and the preregistered 2× uncached cost
   and median latency tolerances. Verify project entitlement, spend exposure
   and data controls through the owner. The credential is a dedicated
   project-scoped key in root-owned mode 0600 `credential-<version>`. Only the
   private approval contains its SHA-256. Prepare root-owned mode 0600
   `approval.json` only after this authorization. The exact fields and types
   are enforced by `verify_approval` in
   [the study CLI](../../backend/scripts/planner_study.py).

Only the trusted owner invokes the
[launcher](../../backend/scripts/planner_study_launch.py) with isolated Python
(`python3 -I`), the approved runner interpreter and backend paths, and the
dedicated UID/GID. The launcher starts one unprivileged worker. The worker
authenticates its root parent through the inherited Unix socket and checks the
current identities and offline controls before acknowledging readiness.
The launcher exclusively creates `claimed`, syncs the parent, writes the
approval digest receipt and syncs the claim and evidence directories before
sending the credential. The child cannot unlink or replace the claim. The claim
is independent of checkout, manifest, approval, credential and study database.
Any existing entry, even an empty directory, permanently consumes the study.
Never remove it or recreate the root. If the filesystem reports an uncertain
claim write, stop and preserve the state. An unsynced write can be lost on power
failure, but the launcher cannot release a credential before successful sync.
The owner must treat such a host incident as terminal.

Closing the launcher channel stops the next guarded operation. The worker
also checks approval expiry at dispatch and enforces a hard process deadline.
An in-flight request can still complete remotely. After verifying the actual
serialized request and current identities, the guard durably reserves the
scheduled slot before forwarding. It checks the actual returned model label on
every response, starting with the first authorized slot. There is no separate
model probe. Wrong identity, incomplete response, auth/quota/HTTP failures,
transport uncertainty, malformed evidence, scope/RLS failure, unsafe SQL,
renderer/conformance/runtime failure and ledger failure stop both arms.
Valid clarification, refusal and semantic misses retain their preregistered
scoring. The guarded output passes through the existing production structured
parser and governed read-only PostgreSQL runtime.

Inspect `claimed/evidence/ledger/slots.sqlite3` read-only, including its
`study` seal and ordered `slots` rows. A pending row is possible exposure and
bars replay. The completed seal is written only after 32 durable, read-back
observations and a final identity check. Evidence contains fixed identifiers,
digests, stages, the verified model label, bounded usage/latency and safe
failure codes. It excludes raw provider payloads, prompts, plans, SQL, result
rows and credentials. Preserve the claim and evidence even if the run fails.
There is no resume or replacement. Revoke the dedicated credential after the
attempt and retain the protected claim. Study results are diagnostic and do
not satisfy [V1 quality gates](../evaluation/v1-quality-gates.md).

## Additional offline verification

The default backend tests exercise the fake transport, claim race, process
termination and persistence failures. For the real PostgreSQL check, use a
fresh database from the offline procedure after migration and before
`initialize`. Run `pytest tests/planner_study_live_postgres.py` from `backend/`
with `PLANNER_STUDY_TEST_DATABASE_URL` and `PLANNER_STUDY_TEST_OWNER` set to its
synthetic URL and ownership receipt. This test initializes and mutates its own
database to exercise drift. The Linux privilege check uses a separate empty
ext4/XFS test mount under a root-owned parent. Run
`pytest tests/planner_study_linux.py` as root with the test mount in
`PLANNER_STUDY_LINUX_TEST_ROOT`. Neither test uses the canonical state root,
an executable approval or a real credential.
