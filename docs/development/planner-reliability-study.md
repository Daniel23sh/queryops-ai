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

## Activation engineering and live approval

The activation implementation is study-only. It keeps the preregistered request
bodies and scoring. Both study profiles now disable SDK and transport retries
and redirects. The official Responses endpoint, verified TLS, 45-second HTTPX
phase timeout, `store=false` and 2,048 output tokens per response are fixed. The
ceiling is 32 logical slots, 32 physical forwards and 65,536 output tokens across
32 responses.
A physical forward is entry into the underlying transport. Its presence cannot
prove receipt or billing, and a timeout can leave both unknown. Input byte counts
in the new manifest inform updated token and cost estimates. Estimates and
telemetry do not cap the bill.

The local activation uses one CLI process under the developer's existing macOS
account. The fixed state directory is the account's actual home (resolved from
the OS user database, independent of `HOME`), followed by
`Library/Application Support/QueryOps/queryops-planner-study-v1`. There is no
state-path override. The directory must be outside the checkout, owned by the
current account and mode 0700. Its files are regular, non-symlink, current-user
owned mode 0600 files. Linux privilege separation, a dedicated system user,
`findmnt`, filesystem-type checks, immutable installations, root-owned files
and the launcher/socket handoff are removed. The same portable local code runs
in offline Linux CI; there is no second activation architecture.

After this PR merges, the operator must complete these steps before live use:

1. Verify all six final-main CI gates on the exact merged SHA. Use a clean `main`
   checkout with matching `origin/main`, normal visible index entries, and exact
   tracked Git blob bytes/modes. Ignored local files such as `.venv` are allowed;
   untracked non-ignored files are rejected. Do not edit source or install/change
   dependencies during the attempt. No root ownership or separate venv location
   is required. The manifest binds actual Python/dependency versions, the
   resolved interpreter and its SHA-256, and the environment path. Use the same
   interpreter/environment for preparation and execution.
2. Prepare a separate owned PostgreSQL 16 cluster using the offline procedure.
   Run the offline integration checks below on their own disposable database.
   Then initialize the candidate database, regenerate the manifest from the
   exact merged source and runtime, and complete a fresh dry-run. Keep the
   candidate database and policies quiescent and unchanged throughout the
   window. Preserve stopped W9 and both terminal W6c journals.
3. Prepare the fixed private state directory without creating `claimed`.
   Never overwrite an existing study's state or copy it to obtain another
   attempt. Place regenerated `manifest.json`, `database-url` and `database-owner`
   there as private files. Inspect `state_identity()` in
   [the activation helpers](../../backend/scripts/planner_study_activation.py)
   to obtain the host digest (OS, hostname and architecture), state path,
   device/inode and current account UID/GID for authorization. Hostname identity
   is an accidental-mismatch check, not hardware attestation.
4. Obtain separate explicit authorization binding the final source and manifest
   digest, both effective profile fingerprints, all request hashes, all 32
   ordered named slots and schedule digest, official endpoint, requested and
   expected returned model, project ID, exact credential identity/version,
   host/state identity and `operator_uid`/`operator_gid`. Bind a whole-second
   UTC start and expiry (`Z` suffix), 32 logical slots/physical forwards,
   per-slot/total output limits, refreshed input-token/dollar estimates, and
   the preregistered 2× uncached cost and median-latency tolerances. Verify
   project entitlement, spend exposure and data controls through the owner.
5. Only after authorization, store the dedicated project-scoped key in private
   `credential-<version>` and the exact private `approval.json` using schema
   `queryops-planner-study-local-approval-v1`. Only the private approval contains
   the credential SHA-256. Do not put the key in the repository, command line,
   environment or evidence. Old Linux approvals cannot authorize this path.
   Exact fields/types are enforced by `verify_approval` in
   [the study CLI](../../backend/scripts/planner_study.py).
6. From `backend/`, the separately authorized operator runs
   `.venv/bin/python -B -m scripts.planner_study live`. The command has no
   credential or state-path argument. It fails closed without the private
   approval and matching source, runtime, database, scopes and credential.

The process completes offline controls, atomically creates `claimed`, syncs its
parent, writes/syncs an approval-digest receipt and syncs its evidence directory
before constructing any network transport. An existing entry, including an
empty directory or symlink, rejects concurrent activation and every repeat.
A failure after claim creation consumes the attempt even if zero requests were
forwarded. There is no resume, replacement or automatic cleanup. Preserve the
claim after interruption, errors or uncertain writes.

The SQLite ledger uses `synchronous=EXTRA` and `fullfsync=ON`. The guard durably
commits and reads back the named slot reservation before entering the underlying
transport. It rechecks source/runtime/database/authorization identities and the
approval/claim and expiry before dispatch. A monotonic deadline plus a process
alarm bounds the approved window; Ctrl-C/process death leaves the claim intact.
An in-flight request can still complete remotely. The actual returned model is
checked starting with the first authorized slot, without a separate model probe.
Wrong identity, incomplete response or telemetry, auth/quota/HTTP failures,
transport uncertainty, malformed evidence, scope/RLS failure, unsafe SQL,
renderer/conformance/runtime failure and ledger failure stop both arms. Valid
clarification, refusal and semantic misses retain preregistered scoring. Output
passes through the production structured parser and governed read-only
PostgreSQL runtime.

Inspect `claimed/evidence/ledger/slots.sqlite3` read-only, including the `study`
seal and ordered `slots` rows. A pending row is possible exposure and bars replay.
A completed seal requires 32 durable, read-back observations and a final identity
check. Evidence contains fixed identifiers, digests, stages, verified model
labels, bounded usage/latency and safe failure codes. It excludes raw provider
payloads, prompts, plans, SQL, result rows and credentials. Revoke the dedicated
credential after the attempt; keep the claim and evidence. Study results remain
diagnostic and do not satisfy [V1 quality gates](../evaluation/v1-quality-gates.md).

### Reduced replay guarantee

The claim and ledger prevent accidental duplicate execution while the local
state remains intact, including after normal crashes, interrupted requests,
pending reservations and SQLite failures. The machine owner can deliberately
delete or alter state, change the OS account/home, copy a credential to another
machine, or restore an earlier filesystem snapshot. This design does not resist
those actions or privileged replay. Never treat missing/restored evidence as
permission to rerun. Power-loss/storage durability is limited by the local OS,
filesystem and hardware; an uncertain write or host incident is terminal for
the operator. Sync failures never permit a forward.

## Additional offline verification

Run the default backend tests, including `tests/test_planner_study.py` and
`tests/test_planner_study_activation.py`, on macOS. They exercise fake Responses
transport, all 32 slots, atomic claim races, replay, SIGKILL, deadline expiry,
private-file checks, identity drift, timeout and persistence failures. Every
activation test redirects state to a fresh temporary directory and uses a
synthetic key and test-only approval; none touches canonical state.

For PostgreSQL, prepare a fresh owned cluster/database with the offline procedure
through migrations/comment, **before** `initialize`. Run
`pytest tests/planner_study_live_postgres.py` from `backend/` with
`PLANNER_STUDY_TEST_DATABASE_URL` and `PLANNER_STUDY_TEST_OWNER` set to its URL
and ownership receipt. It initializes and deliberately mutates its database,
verifies denied/RLS controls, runs the complete local activation with a fake
transport and rejects post-dispatch database drift. Do not reuse that mutated
database as the study candidate. The PostgreSQL Security CI gate runs this
explicit test on its own PostgreSQL service; all CI calls remain synthetic.
