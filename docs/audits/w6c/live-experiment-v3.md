# W6c v3 — offline preparation and separate live-approval contract

The owner authorized **preparation/implementation only on 2026-11-04**. This
separately versioned one-shot diagnostic is exposed, focused evidence. It is not
a fresh held-out generalization test, V2 Evaluation qualification, or V1 release
readiness. No provider execution, availability probe, retry/resume, substitution,
operator-approval file, W9 work or merge is authorized by this preparation.

## Frozen selection and configuration

[Configuration](live-v3.json) selects exactly this sequence from the original
[frozen corpus](heldout-v1.json), verified through [freeze.json](freeze.json):

| Order | Case | SHA256 of exact UTF-8 question bytes |
| --- | --- | --- |
| 1 | W6C-008 | `5b1de9593549dc6ab40865fbdea32a7e1df2757a2ce98fd7716cfb74af7d3295` |
| 2 | W6C-011 | `502c7b2caeda3a607a224fad66b2bf5154cb217ed02efcc0c2ec8833cd39942c` |
| 3 | W6C-012 | `662a5d7d632d143bf8f1a278d2cb67c83ac0e8d50ef6304f4ff6277c4c2bad47` |
| 4 | W6C-013 | `4ebcc73c3ba2bc523ecbbf41413abf40ea71969e0118f4cfd84df4c57d781f1a` |
| 5 | W6C-020 | `c953922c63eb80f9e755c51c0aac7adc46c15712a4b3ea5d1008ed86cba71ddd` |
| 6 | W6C-007 | `1f62a0f8902db8e25cad7549202d04d034a3bcca5525c353fae96a347c3771b3` |

The six successful historical cases (001/002/003/004/006/009) are excluded. The
[post-live diagnosis](post-live-diagnosis-he.md) explains why 008 is unresolved,
007 failed without usable outcome evidence and 011/012/013/020 were never sent.
Original questions, acceptance criteria, fixtures and independent oracles retain
their original bytes/meaning. The existing F1 adapter changes only 007's manual
witness encoding to the supported reverse-LEFT plan; it preserves its oracle.

Runtime stays `gpt-6.1-terra`, Responses API, strict structured SemanticPlan,
reasoning `low`, output cap `2048`, timeout `45s`, SDK/transport retries `0`,
redirects disabled and `store=false`. Product instructions/catalog are unchanged.
V2 dataset digest is `6ac164ab6c58c0b008a65afc01cd26aa434fecd3eaa402b5bdad9c89e6f6540f`;
catalog digest is `918df0c63288b7ed7ce700f8442c82bc1ffa3f51e1f4eaa63fd66012af82adb4`.
Incompatible installed versions fail validation; preparation never silently
changes settings or installs a replacement to make the experiment pass.

## Version, journal and approval boundaries

The v3 entry point is [w6c_v3.py](../../../backend/scripts/w6c_v3.py). The original
[v2 entry point](../../../backend/scripts/w6c_live.py), configuration and historical
contract remain unchanged. Only the shared HTTP guard's fixed class budget is
factored: v2 retains 12/12/1; the v3 subclass requires these exact six IDs/order
and 6/6/1. There is no CLI budget/version/endpoint/journal override.

Schemas are distinct: `queryops-w6c-live-v3`, `queryops-w6c-preflight-v3`,
`queryops-w6c-diagnostic-result-v3`, `queryops-w6c-operator-approval-v3`. A v2
manifest or approval cannot authorize v3. The complete manifest is recomputed
before constructing the HTTP client. Before every physical dispatch, source,
freshness, frozen inputs/config, runtime/dependencies/credentials, data fingerprint,
security policy and effective authorization/request-body identity are rechecked.

The **fixed OS-account** journal is
`~/.local/state/queryops/w6c-live-v3/dispatch.jsonl`, derived from the OS account
record, never environment `HOME`. It is separate from v2 and shared across
checkouts/source revisions. Only an approved live path creates its directory.
Ancestor ownership/writability/symlinks are checked; newly created directory
entries are fsynced, the final directory is owned mode 0700, the journal is
exclusive mode 0600. `O_EXCL` rejects every existing file/symlink and concurrent
start. Reservation is written/fsynced before touching the underlying transport;
completed safe case evidence is fsynced before the next call. No reset, deletion,
resume or retry route exists, including after partial/fatal/interrupted execution.
A reservation without a response has unknown usage and permanently spends its
attempt. This trusts the local operator; it cannot restrain an OS administrator
who deletes state or runs an unrelated HTTP client.

Preparation/dry-run use only an automatically removed temporary journal. CLI
inputs/outputs cannot point into either real live-journal directory, including
through resolved symlinks. Neither operation creates, reads, reuses or consumes
a live journal. The v2 terminal journal must never be reset or reused.

## Offline preflight and dry-run

Use a **new isolated disposable PostgreSQL 16 cluster**, with an empty database
named exactly `queryops_w6c_v3_test`. Never adopt/reset an existing user database,
cluster, role or container. Set `POSTGRES_TEST_DATABASE_URL` to its synthetic
loopback URL, `POSTGRES_TEST_DATABASE_DISPOSABLE=1`, and `DATABASE_URL`/`POSTGRES_DB`
to different application DB names. Fresh initialization refuses nonempty public
schemas. Existing migration role-collision protection remains authoritative.

From a clean committed checkout, in `backend/` (replace the reference with the
actual current UTC time; maximum age 24h, future skew 5 minutes):

```sh
.venv/bin/python -m scripts.w6c_v3 --initialize \
  --reference-time 2026-11-04T00:00:00+00:00 --out /tmp/w6c-v3-preflight.json
.venv/bin/python -m scripts.w6c_v3 --manifest /tmp/w6c-v3-preflight.json \
  --dry-run --out /tmp/w6c-v3-dry-run.json
```

No API key is needed. Preparation creates no HTTP transport; dry-run sends all
six requests through the real SDK parser and fake in-process HTTP transport.
A network-isolated runtime can share only the fresh PostgreSQL container's
loopback network namespace. Synthetic dry usage is not billable usage evidence.

The secret-free manifest binds clean source SHA, fresh UTC reference, frozen
hashes, config, per-case authorized schema/catalog/prompt/request hashes, dataset,
full data fingerprint/counts, actual Python/package/PostgreSQL versions, provider
runtime identity, dependency manifest, migration and role/grant/RLS identities (including column ACLs and public schema
ownership/ACLs; absent/empty column ACLs both mean no column grant).
It validates query-runtime restrictions/effective read-only grants, scoped RLS,
action-runtime flags, effective query authorization and **all six independent
positive witnesses** under non-owner read-only repeatable-read UTC transactions.
Global reference tables follow the existing domain pack's scope definitions.
No frozen file or product rule is modified. Exact installed versions/fingerprint
and execution evidence are recorded in [the preparation report](v3-preparation-evidence-he.md).

Preserve independent `output_contract_match` and `result_multiset_match`, including
`not_evaluated` for incomparable output identities/no plan. Safe mismatches continue;
unsafe/fatal cases stop before the next question. Transport categories and known/
unknown usage remain bounded and separate from semantic evidence. `sequence_failed`
adds safe fixed stages: client setup, case authorization, logical reservation,
HTTP boundary, dispatch revalidation, SDK parsing, plan safety, oracle comparison
or evidence write. No exception messages, raw provider content, plans, SQL or
rows are persisted. Disk failure may prevent the final failure event, but existing
exclusive journal ownership still prevents another execution.

## Separate post-merge live-approval request

1. Review this focused Draft PR and passing final-head CI plus fresh independent
   V3 correctness/security review. Merge only under a separate user decision.
2. Fetch latest main. Require clean HEAD = local main = origin/main = exact merged
   SHA. Against that source, prepare a **new** isolated cluster/empty v3 database
   with fresh UTC reference and rerun full preflight/dry-run. Feature-branch
   fingerprints prove preparation only and cannot serve as approved live identity.
3. Present the new merged SHA/fingerprint, actual runtime versions, fixture/data/
   policy/config identities, exact ordered IDs/hashes, acceptance/stop rules and
   current cost estimate. Request explicit human authorization for exactly six
   logical calls/six physical attempts/one per question, exact model/config, no
   retry/resume/fallback/substitution, and all terminal conditions. No authorization
   is inferred from passing offline checks or this PR.
4. **Only after that explicit approval**, a separate owned mode-0600 regular JSON
   file outside the repository is created with exactly: schema
   `queryops-w6c-operator-approval-v3`, `approved=true`, `fingerprint`,
   `source_git_sha`, `model=gpt-6.1-terra`, `max_logical_calls=6`,
   `max_physical_dispatches=6`, `max_dispatches_per_question=1`,
   `no_retry_no_resume=true`. The fingerprint binds every other manifest setting.
   Supply explicit live environment (including `OPENAI_MAX_RETRIES=0`), matching
   `--manifest`, `--live`, `--approval` and a new external `--out` file.
5. Preserve both historical journals. If the v3 journal already exists, stop;
   approval, a new manifest, new source or another checkout cannot reset its budget.

Stop this task at the independently reviewed Draft PR. No live approval file or
real provider request belongs in preparation.
