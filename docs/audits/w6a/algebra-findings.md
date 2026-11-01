# W6a F11: supported algebra and comparison diagnosis

These are **19 exploratory, handwritten downstream probes**, not provider
observations, blinded held-out cases, a Canary, or release evidence. No provider
was called. The fixed V2 questions, contracts, baselines, catalog, prompts,
runtime, scoring and gates were not changed. Results are in
[algebra-results.json](algebra-results.json); replay code is
[algebra_probe.py](algebra_probe.py). The common freeze is
[baseline.json](baseline.json).

## Conclusion

F11 is a verified **encoding restriction**, with a narrower evaluator/runtime
contract distinction. It is not evidence that hard-004 is unrepresentable or
that the provider selected an invalid shape. All six canonical alternatives
tested passed plan validation, rendering, renderer self-conformance, governed
PostgreSQL execution, semantic scoring and result comparison. This includes
hard-004 grouped by either `login_events.user_id` or `directory_users.id`.
Its historical diagnostic Canary success remains valid historical counterevidence.

No defect in deterministic rendering of an **accepted grouped plan** was found
in this matrix. Every accepted plan rendered SQL that passed conformance to
that same plan. The separate composition specialist owns the hard-005 duplicate
output-label finding; it is not duplicated here.

## Frozen execution and safeguards

Runtime source is main `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5` with the
documentation approval commit `36591a150528a654f30dc7cc8e48ca46ae5268dc` checked
out. Machine evidence carries source-file hashes, source IDs, exact V2/catalog
identities and the hash of the common freeze. The investigation does not edit
existing files.

Only dedicated disposable container `queryops-w6a-algebra-20261101`, local
port `55448`, database `queryops_w6a_algebra_test` was used. The repository's
`validated_disposable_database_url` guard runs before access, with a different
sibling application database identity and the disposable opt-in. PostgreSQL is
16.14, migration head `0010_disable_inactive_user`, timezone `Etc/UTC`.
Each result records its actual transaction time, snapshot, role, read-only state
and isolation; no clock or timezone override was used.

The medium seed is 42 with explicit reference
`2026-11-01T09:20:36+00:00`. The initial plain-medium database fingerprint was
`8d027d94029ba0fd0e3a3eebcc99fec41b0084140df54a8834ea73560b0eb077`.
Because hard-004 was empty on that seed, a separate deterministic synthetic
contrast added two users, two privileged groups, two memberships per user,
six versus five recent failed logins, and one excluded old failed/success event
per user. IDs and timestamps are deterministic. The resulting fingerprint is
`040b9f787d5728fc61803e0c66bd33bb6690d2738a6caa1d09173afd60cd9201`.
This contrast is identified separately from the original seed, and changes no
dataset or evaluation baseline. Successful rows are recorded as counts and
multiset hashes only, never raw row records.

All executions use the existing authorized baseline helper and executor,
`queryops_query_runtime`, read-only repeatable-read transactions, normal SQL
safety, resource authorization and RLS. Baseline and SQL witness share the
transaction snapshot. Each successful result is below its safety limit and
has complete delivery evidence.

## Decisive matrix

“SQL witness” means a rejected plan's shape is deliberately isolated downstream
through the existing evaluator-only SQL path. It is **not** a plan the product
accepted. Result-only comparison forces semantic-pass status solely to isolate
the comparator; semantic scoring is reported separately in every machine record.

| Probe family | Plan/runtime status | Semantic scoring | SQL/result evidence | Attribution |
| --- | --- | --- | --- | --- |
| medium-006 department ID, name, or both (3) | All accepted; renderer/conformance pass | All pass | 8 rows each; comparison passes | Supported alternatives; non-null unique identity proofs work |
| hard-004 event user FK or directory user PK (2) | Both accepted; renderer/conformance pass | Both pass | 1 qualifying user; comparison passes | Canonical requested business answer is representable |
| hard-006 product-name grain (1) | Accepted; renderer/conformance pass | Pass | 6 rows; comparison passes | Non-distinct SUM supported |
| medium-006 projected department ID with hidden name grouping | Rejected `group_by_incomplete` | Pass in isolated observation | SQL witness 8 rows; comparison passes | Valid equivalent SQL shape outside accepted encoding |
| hard-004 projected event-user FK plus hidden directory PK grouping | Rejected `group_by_incomplete` | Pass in isolated observation | SQL witness 1 row; comparison passes | Same restriction with selected INNER/FK equality |
| medium-006 projected name, grouped only by PK | Rejected `group_by_incomplete` | Fails projected-grain evidence | PostgreSQL permits PK dependency; witness 8 rows; result-only comparison passes | Three different contracts: SQL legality, plan encoding, semantic observation proof |
| medium-006 all group keys omitted from output | Accepted; renderer/conformance pass | Fails grain evidence | 8 measure-only rows; comparison fails | Hidden grouping is accepted when outputs are entirely empty; this does not satisfy the evaluation request's projected identity |
| medium-006 extra user-status dimension | Accepted; renderer/conformance pass | Fails grain/grouping | 16 rows; comparison fails | Correctly distinguishes changed population grain from redundant dependent grouping |
| hard-004 non-distinct event count; same with query-level DISTINCT (2) | Both accepted; renderer/conformance pass | Both fail aggregation semantics | 2 qualifying rows each; comparison fails | Membership fanout changes COUNT; SELECT DISTINCT cannot repair aggregation grain |
| hard-004 projection retained but grouping removed | Rejected `group_by_incomplete` | Fails grain/grouping | SQL witness fails safely with database error | Invalid encoding; widening to arbitrary mismatches would admit invalid SQL |
| hard-004 LEFT bridge, event-user FK projection | Accepted; renderer/conformance pass | Passes observation semantics | 1 row on fixture; result comparator rejects | Observation score does not require INNER equality for unchanged FK output; relational comparison remains conservative |
| hard-004 LEFT bridge, directory PK projection | Accepted; renderer/conformance pass | Rejects unproved key equivalence | 1 row on fixture; result-only comparison passes | Sample result agreement is insufficient proof; unrelated INNER path can remove null-extension on this population |
| hard-004 impossible failed/success conjunction, grouped versus scalar (2) | Both rejected `predicate_contradiction` | Grouped observation passes; scalar fails | SQL witnesses return 0 grouped rows versus 1 scalar aggregate row; comparison fails | Rejected-plan isolation only; demonstrates empty-set grouping law, not accepted runtime behavior |
| hard-006 SUM DISTINCT | Rejected `sum_distinct_unsupported`; renderer also refuses witness | Fails aggregation semantics | Not executed | Explicit unsupported algebra, not a renderer regression |

The shared literal structural comparator intentionally reports mismatches for
the department-ID and equivalent user-PK alternatives against the contract's
literal canonical fields, while the semantic evaluator and actual results pass.
It performs no relational equivalence and is not runtime/evaluation authority.
Cross-checking a SQL alternative against another canonical plan similarly
produces conformance output/grouping mismatches. That is expected: conformance
proves implementation of the **selected plan**, rather than all equivalent SQL.
Renderer self-conformance and cross-plan conformance are separate machine fields.

## Mechanism and competing hypotheses

- **R1 — supported business question cannot be expressed:** contradicted for
  all inspected existing request families by six successful canonical forms.
  General requests for AVG, arbitrary expressions/subqueries, SUM DISTINCT or
  arbitrary hidden grouping are outside this bounded count/SUM plan grammar;
  this work does not authorize expanding it.
- **R2 — planner can choose a SQL-legal encoding rejected by runtime:** confirmed
  as a deterministic possibility. `semantic_plan.py:435–438` requires exact set
  equality between output and grouping fields when both output and aggregation
  exist. It rejects redundant hidden grouping even when evaluator identity
  proofs accept the grain. No actual provider selection frequency is measured.
- **R3 — renderer corrupts supported grouping/count semantics:** not reproduced
  for accepted plans here. Fanout wrong-count variants faithfully implement
  their selected, semantically wrong plans. This distinction matters: query
  conformance cannot infer an omitted business count DISTINCT requirement.
- **R4 — evaluator should accept any same-sample answer:** rejected. Extra
  dimensions, incorrect COUNT, missing projected identity and outer joins are
  counterexamples. Result-only pass and observation-semantic pass are not
  interchangeable, especially for empty sets and incomplete identity proof.

Authoritative source IDs and exact file hashes are in the JSON `sources` array:
`F11-runtime` (`semantic_plan.py:435–473`), `F11-renderer`
(`sql_renderer.py:28–82,128–159,268–285`), `F11-conformance`
(`semantic_conformance.py:870–908`), `F11-evaluator`
(`scoring.py:147–197`), `F11-identity` (`identity.py:1–118`), and
`F11-literal` (`structural_intent_comparison.py:1–99`).
The provider instruction text (`F11-prompt`, `openai_provider.py:66–104`)
describes output forms and scalar metric shape, but does not state the exact
output/grouping set equality explicitly. That is a plausible encoding-friction
mechanism, not measured evidence of model error.

## Smallest W6b recommendation and acceptance

**Do not widen grouping/conformance/evaluator equivalence on this evidence.**
Keep the canonical supported algebra. In a separately approved correction,
make the output/grouping encoding restriction explicit to the planner and
retain positive/negative contract examples. This is smaller than general SQL
algebra expansion; it cannot establish a quality improvement without separately
measured model behavior. The composition specialist's demonstrated output
identity collision is a distinct deterministic issue and can take priority.

If later evidence justifies normalization of redundant hidden grouping, make
that a separately bounded decision: prove equivalence from authoritative
non-null unique keys and selected INNER FK equality, preserve required outputs,
and never remove a population dimension or infer equivalence from matching
sample rows. Do not weaken the evaluator or baselines to accept invalid output.

Acceptance must preserve the six canonical positives, the two redundant-key
contrasts, negative fanout COUNT and query-DISTINCT cases, extra dimensions,
missing projected identity, invalid no-grouping SQL, LEFT/null extension, empty
grouped/scalar behavior and SUM DISTINCT rejection. Existing PostgreSQL tests
already supply nullable counts, second-branch fanout, orphan-reference versus
INNER/LEFT identity, multiple aggregates and one-to-one cardinality negatives.
An independent author should freeze fresh paraphrases and synthetic relational
fixtures before any W6b tuning; these 19 explored cases are regression candidates,
not unseen held-out validation. Live calls need separate exact-model/case/budget
approval and are not needed to verify the deterministic restriction itself.

## Validation and limitations

The probe's assertions passed for all 19 contrasts. Existing
`tests/test_relational_semantics.py` passed **33 tests, zero skipped** against
this dedicated PostgreSQL instance. Its seven formerly skipped PostgreSQL cases
use temporary tables and rollback, preserving the medium-plus-contrast data.
Ruff and Python syntax checks passed for the new script. Commands and focused
log hash are in the JSON; safe logs are `/tmp/queryops-w6a/algebra-probe.log`,
`algebra-migrate.log`, and `algebra-relational-tests.log`.

No provider accuracy, provider-stage failure rate, qualifying Canary, Full40,
release gate, browser behavior, or independent non-author review is claimed.
Database clocks naturally advance; replay transaction/snapshot metadata changes.
No real identities, credentials, SQL text or result rows are stored in the report.
The diagnostic fixture remains only in its disposable container for review.

Investigation writes stopped after final artifact verification; no files staged
or committed by this specialist.
