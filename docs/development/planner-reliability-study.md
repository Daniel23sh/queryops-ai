# Planner reliability study

This exploratory diagnostic compares `gpt-6.1-terra` reasoning `low` and `medium`.
The preparation harness is offline-only. V1 remains unqualified after the first W9
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

Before enabling live execution, separately review the activation path, pin a
canonical study-specific ledger location across checkouts, and prove an existing
or pending claim bars every replay. Confirm the returned model label using
bounded provider evidence. Regenerate the study manifest against the
exact clean source that will execute. Reverify the database, dependencies, both
profile hashes and request hashes. Require explicit owner approval for that
manifest, official endpoint, access on the intended OpenAI project, secure
credential source, UTC window, the 32 named slots and the exposure below.
Stop both arms on context or identity drift, authorization/RLS failure,
unsafe execution, renderer/conformance or runtime failure, malformed evidence,
ledger failure, provider authorization/quota failure or expiry. Inspect durable
evidence before progression. Do not replace a slot or use the W9 environment or
terminal W6c journals.

At SDK 2.46.0 and HTTPX 0.28.1, the profile's two retries and 20 redirects allow
96 SDK tries and a derived 2,016 physical dispatches across 32 logical calls.
Output allowance is 65,536 tokens for one response per logical call, including
reasoning. Record actual bounded attempts and tokens separately. Per-prompt
serialized input byte counts are in the manifest and should be used to refresh
token and cost estimates before approval. Standard uncached rates and retries
give planning estimates, with caching and unobserved failure usage adding
uncertainty. The derived dispatch ceiling and telemetry are not billing caps.
The study does not satisfy [V1 quality gates](../evaluation/v1-quality-gates.md).
