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

Use native PostgreSQL 16 tools (`initdb`, `pg_ctl`, `createdb`, `psql`) on
`PATH`, plus the existing backend virtual environment. No Docker, VM, Linux,
root privileges or system service is needed. Start a fresh dedicated cluster
under the current macOS account, with a random loopback port and password.
The connection user owns the empty study database. From `backend/`:

```bash
umask 077
study=$(mktemp -d /tmp/queryops-planner-study.XXXXXXXX)
study=$(cd "$study" && pwd -P)
db=planner_study_test_$(openssl rand -hex 8)
password=$(openssl rand -hex 24)
port=$(.venv/bin/python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
openssl rand -hex 16 > "$study/owner"
printf '%s\n' "$password" > "$study/postgres-password"
mkdir "$study/socket"
initdb -D "$study/pgdata" -U queryops --pwfile="$study/postgres-password" \
  --auth-local=scram-sha-256 --auth-host=scram-sha-256 --encoding=UTF8 --locale=C
pg_ctl -D "$study/pgdata" -l "$study/postgres.log" \
  -o "-h 127.0.0.1 -p $port -k $study/socket" -w start
PGPASSWORD="$password" createdb -h 127.0.0.1 -p "$port" -U queryops "$db"
PGPASSWORD="$password" psql -h 127.0.0.1 -p "$port" -U queryops -d postgres \
  -v ON_ERROR_STOP=1 -c "COMMENT ON DATABASE $db IS 'queryops-planner-study:$(cat "$study/owner")';"
export PLANNER_STUDY_DATABASE_URL="postgresql+psycopg://queryops:$password@127.0.0.1:$port/$db"
printf '%s\n' "$PLANNER_STUDY_DATABASE_URL" > "$study/database-url"
DATABASE_URL="$PLANNER_STUDY_DATABASE_URL" QUERYOPS_APP_DATABASE_ROLE=queryops .venv/bin/alembic upgrade head
DATABASE_URL="$PLANNER_STUDY_DATABASE_URL" .venv/bin/alembic current
DATABASE_URL="$PLANNER_STUDY_DATABASE_URL" .venv/bin/alembic check
.venv/bin/python -B -m scripts.planner_study initialize --owner-receipt "$study/owner"
.venv/bin/python -B -m scripts.planner_study manifest --owner-receipt "$study/owner" --manifest "$study/manifest.json"
.venv/bin/python -B -m scripts.planner_study dry-run --owner-receipt "$study/owner" --manifest "$study/manifest.json" --evidence "$study/dry-run"
```

Keep the cluster, database and roles unchanged between manifest, dry-run and
any separately authorized live attempt. A port collision fails startup; choose
a new port before preparing a manifest. The short `/tmp` path avoids macOS Unix
socket path limits. Keep a future live cluster available and quiescent for the
approved window; do not reset it or use the application, W9 or W6c databases.
Only stop this owned temporary cluster with `pg_ctl -D "$study/pgdata" -w stop`.
Do not remove historical evidence or a canonical claim during cleanup.

The harness accepts only the expected PostgreSQL driver, loopback endpoint,
database name, owner receipt, and migration head. Initialization refuses a
nonempty database. The dry-run SDK uses an in-process mock transport and a
non-secret placeholder. Its fresh diagnostic ledger commits every reservation
before generation. A pending slot or write failure prevents progression.
It retains only bounded result stages and usage. Preparation never reads a
live credential, creates a canonical claim or makes a real provider request.

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

## Local execution

The owner has authorized one bounded comparison of `gpt-6.1-terra` at `low`
and `medium`. This cleanup and its tests make zero real provider requests.
The study is diagnostic and cannot satisfy [V1 quality gates](../evaluation/v1-quality-gates.md).

Use the existing backend environment, native PostgreSQL and API key. The live
command reads `OPENAI_API_KEY` from the process environment, or from the repository
root `.env` when it is not exported. Only that key is read from `.env`; ordinary
application model/reasoning settings do not alter the frozen study profiles.
The local file must be regular, account-owned and not writable by other accounts.
Quoted values, an `export` prefix and inline comments are supported; interpolation
is not performed. Duplicate or invalid key entries fail closed. The key is never
copied to study state, logged or included in evidence. No new key, credential
version/hash, project ID or `OpenAI-Project` header is required. Project and
organization headers are omitted, including values inherited from the environment.

There is no private approval file, repeated identity form, host identifier,
account-ID entry, UTC window or mandatory cost estimate. The single explicit
execution gate is `--allow-paid-study`, which acknowledges this bounded paid
attempt. A missing flag rejects live execution before credential access or a
network transport. The flag is rejected for offline preparation commands.

After the cleanup merges and all six final-main CI gates pass:

1. Use the clean merged checkout and the existing backend environment. Keep source
   and dependencies unchanged for the attempt. Exact HEAD, tracked blob bytes and
   modes, visible index entries, actual Python/interpreter and dependency versions
   remain verified; a branch name is not an identity. No root-owned checkout or
   separate environment is needed.
2. Reuse the unchanged, owned synthetic PostgreSQL 16 environment from preparation,
   or prepare a fresh one with the offline procedure. Do not initialize an already
   populated candidate again. Regenerate a new manifest for the merged source and
   run a fresh supplied-plan dry-run. Keep old manifests/evidence; never overwrite
   them to hide a mismatch. Do not use W9, W6c or the application database.
3. Run the command below once using the same database URL, owner receipt and
   manifest already used offline. Existing prepared bundles contain `database-url`
   and `owner`; there is no extra copy into canonical state. `.env` supplies the
   existing key automatically.

From `backend/`, with `study` pointing to the private prepared directory:

```bash
export PLANNER_STUDY_DATABASE_URL="$(cat "$study/database-url")"
.venv/bin/python -B -m scripts.planner_study manifest \
  --owner-receipt "$study/owner" --manifest "$study/manifest-after-merge.json"
.venv/bin/python -B -m scripts.planner_study dry-run \
  --owner-receipt "$study/owner" --manifest "$study/manifest-after-merge.json" \
  --evidence "$study/dry-run-after-merge"
# Separately from offline validation, execute the already authorized attempt once:
.venv/bin/python -B -m scripts.planner_study live --allow-paid-study \
  --owner-receipt "$study/owner" --manifest "$study/manifest-after-merge.json"
```

The CLI displays derived input-token estimates and the output ceiling without
requiring estimate fields. The 2026-11-11 preparation estimated approximately
295,871 input tokens from recorded UTF-8 bytes / 4 and about $0.62 at Standard
uncached rates, including the full output ceiling. See [published pricing](https://developers.openai.com/api/docs/models/gpt-6.1-terra).
These are planning estimates, not measured token counts or dollar caps. The
manifest retains per-case input-byte counts; refresh estimates when regenerating
it. The advancement scorer still applies its preregistered 2× uncached-equivalent
cost and median-latency tolerances after complete telemetry is available.

## Safeguards and evidence

The command creates private local state automatically at the OS account's actual
home (independent of `HOME`), followed by
`Library/Application Support/QueryOps/queryops-planner-study-v1`. There is no state
path override, Docker, Linux host, VM, root privilege or dedicated system user.
Old configuration files can remain as historical preparation artifacts; they are
not execution inputs. Never delete or reset an existing `claimed` entry.

Preflight revalidates the manifest and runs offline authorization/RLS controls.
Only then does the process atomically create `claimed`, sync its parent, write
and sync `manifest.sha256`, and prepare the private evidence directory. Any existing
entry, including a symlink or empty directory from an interrupted start, consumes
the study and rejects another activation. Failure after claiming is terminal even
if zero requests were forwarded. There is no resume, replacement or cleanup path.

Both SDK and transport retries and redirects are disabled. The official Responses
endpoint, verified TLS, `store=false`, 45-second HTTP phase timeouts and 2,048 output
tokens per response remain fixed. The ceiling is 32 logical slots, 32 physical
forwards and 65,536 output tokens. A derived process deadline of 32 × 45 seconds
(24 minutes after preflight) also bounds accumulated I/O phases. An in-flight
request can complete remotely after interruption, and its billing can be unknown.

The SQLite ledger retains `synchronous=EXTRA` and `fullfsync=ON`. Every scheduled
reservation is committed and read back before the underlying transport is entered.
The guard checks the actual serialized request hash, endpoint, model profile and
API-key authorization header. It rejects project/organization headers. Source,
runtime, actor/exact scopes and database/policy/data fingerprints are checked when
building context, immediately before forwarding and after the provider response.
These checks protect different points in the request/execution sequence. The
claim's device/inode and receipt are checked throughout; redundant host and
approval-file checks are removed. The actual returned model and complete bounded
usage are verified on every response, beginning with the first scheduled slot;
there is no separate model probe.

Wrong identity, unsafe SQL, scope/RLS failure, renderer/conformance/runtime failure,
malformed/incomplete responses or telemetry, auth/quota/HTTP failure, timeout,
transport uncertainty or persistence failure stops both arms. Valid clarification,
refusal and semantic misses keep the unchanged preregistered scoring. Output uses
the production structured parser, deterministic renderer, SQL validation,
conformance and governed read-only PostgreSQL execution.

Inspect `claimed/evidence/ledger/slots.sqlite3` read-only, including the `study`
seal and ordered `slots` rows. A pending row is possible exposure and bars replay.
A completed seal requires 32 durable read-back observations and final identity
verification. Evidence contains fixed identifiers/digests, stages, model labels,
bounded usage/latency and safe failure codes. It excludes keys, provider payloads,
prompts, plans, SQL and result rows. Preserve the claim and ledger on every outcome.
Do not rotate or revoke the reused application key as automatic study cleanup.

### Reduced replay guarantee

The fixed claim and durable ledger prevent accidental duplicate execution while
local state remains intact, including after normal crashes, interrupted requests,
pending reservations and SQLite failures. They do not resist the machine owner
altering/deleting state, changing accounts/homes, copying credentials or restoring
an earlier filesystem snapshot. The CLI intent flag replaces a separately signed
or manually prepared authorization record; it is not a multi-user permission
boundary. Source/runtime/data consistency, backend authorization and RLS remain
independent checks. Power-loss/storage durability depends on the local filesystem
and hardware; an uncertain write or host incident is terminal. Sync failures never
permit a forward. No diagnostic result qualifies V1 for release.

## Offline verification

Run `tests/test_planner_study.py` and `tests/test_planner_study_activation.py` on
macOS with fake transport. Tests use synthetic keys and temporary state, exercise
all 32 requests, existing `.env` parsing without a Project ID, the explicit CLI
gate, claim races, replay, SIGKILL, deadline expiry, identity drift and transport/
persistence failures. They never use the operator's key or canonical claim.

For PostgreSQL, prepare a separate fresh owned cluster/database with the offline
procedure through migrations/comment, **before** `initialize`. From `backend/`,
run `pytest tests/planner_study_live_postgres.py` with
`PLANNER_STUDY_TEST_DATABASE_URL` and `PLANNER_STUDY_TEST_OWNER`. It initializes and
deliberately mutates its own database, verifies denied/RLS controls, completes
fake 32-slot activation without manual approval or credential files and rejects
runtime/database drift. Do not reuse that mutated database as the candidate.
The PostgreSQL Security CI gate runs this explicit check on a separate synthetic
PostgreSQL service. All six CI gates remain unchanged; every CI request is fake.
