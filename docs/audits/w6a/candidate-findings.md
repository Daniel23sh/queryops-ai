# W6a candidate recall and catalog-context diagnosis

Investigation only. Source/runtime identities are frozen in
[baseline.json](baseline.json). The probe checks that production/application,
scripts and tests still match `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`
and that the catalog matches the freeze. No provider call, database connection,
database write, SQL execution or semantic correction occurred.

## Reproduce and denominators

From `backend/`:

```bash
PYTHONPATH=. .venv/bin/python ../docs/audits/w6a/candidate_probe.py
.venv/bin/ruff check ../docs/audits/w6a/candidate_probe.py
```

[candidate_probe.py](candidate_probe.py) writes
[candidate-results.json](candidate-results.json). Synthetic questions and
prespecified expected catalog IDs are in
[candidate-cases.json](candidate-cases.json), authored before the first probe.
Corpus SHA-256:
`203afe0e190bbcf4d569a596697a414c552496efae967577613ae51c5f9253e9`.

There are **79 exploratory cases**: 38 vocabulary cases across all 11 catalog
entity families, 24 business-definition cases across eight families, seven
relationship cases across three families, and ten controls. This is a purposive
stress corpus, not sampled user traffic, an independent holdout, or a release
benchmark. Some vocabulary targets (subscriptions, business units, access roles,
entitlements) are domain hypotheses requiring product judgment. Their inclusion
does not establish that every such phrase should automatically resolve.

The real `build_schema_context`, `UserAccessContext`, access policy,
`_user_generation_context` and candidate builder run unchanged. Only database
resource loading is replaced with **unpersisted ORM metadata derived from the
existing seed resource specifications**. Global scope and effective permission
are supplied explicitly; role is `None`. This exercises the real permission
decision, not role-name substitution. It does not verify persisted resources,
permission resolution, PostgreSQL grants, RLS, or API behavior. Two missing-column
controls intentionally inject narrower post-projection contexts; production
schema projection itself currently supplies domain-pack columns.

Each expected item is checked separately for catalog existence, authorization
eligibility, and final candidate presence. All positive expected IDs exist in the
catalog and are authorized under this fixture. Therefore positive misses here
are context retrieval/retention failures, not missing catalog records or denied
authorization. Controls are excluded from the positive recall denominator.
Metrics count repeated expected IDs across cases, not distinct catalog IDs.

| Measurement | Positive denominator | Present in projection |
| --- | ---: | ---: |
| All expected items in a case | 69 cases | 40 (58.0%) |
| Entity target occurrences | 91 | 56 (61.5%) |
| Concept target occurrences | 40 | 30 (75.0%) |
| Relationship target occurrences | 13 | 7 (53.8%) |
| Composition-rule target occurrences | 6 | 3 (50.0%) |
| Named-metric target occurrences | 3 | 3 (100%; one metric family) |

These are **candidate availability**, not provider selection, interpretation,
SQL correctness, or final-answer scores. A missing rule can sometimes be
represented using another supported plan form. Entity absence is stronger:
`validate_semantic_plan` rejects selection outside the projection with
`entity_not_candidate` even if the table appears in the broader authorized schema.

## Failure matrix and counter-evidence

| Family/contrast | Observed availability | Attribution / limit |
| --- | --- | --- |
| All 11 canonical entity phrasings | 11/11 correct target entities present | Canonical vocabulary works; this is not a blanket candidate failure. |
| Devices/endpoints versus computers/laptops/desktops/servers | Devices/endpoints present; four other noun variants absent | Exact-reference vocabulary plus narrow description fallback; laptop/desktop requests also need subtype filtering, which entity recall does not test. |
| Managed-server description | `Summarize managed server inventory` selects devices | Description fallback works when two description tokens form a unique winner; a server noun alone is below its threshold. |
| Vocabulary breadth | 20/38 target entities present; at least one miss in 10/11 families | Not isolated to computers/laptops. Only the groups family has all tested variants covered. Domain-hypothesis caveats above apply. |
| Software subscriptions / allocated software seats | Both select only `software_installs`; target licenses/assignments absent | A matching generic noun can produce misleading context and suppress description fallback. This is not evidence the provider chose the wrong entity. |
| Business definitions | 16/24 cases have all targets; six entity misses, two definition-context misses | Most entity-backed paraphrases retain definitions. Unanchored business language loses both entity and definitions. |
| Non-compliant posture | Canonical wording and posture phrasing retain the rule; expanded Boolean wording retains its three concepts but omits the rule | Named-rule retrieval depends on its references. Literal/Boolean expressibility and correct selection need separate validation. |
| Disablement review expanded wording | All 11 entities appear through complete relationship closure, but `privileged_group` and `disablement_policy_review` are absent | Connector entities intentionally import no business semantics. Seeing `groups` in the entity list therefore does not prove privilege-definition availability. |
| Relationship families | 4/7 cases complete; 7/13 required relationship occurrences present | All three incomplete cases first lose an anchor entity. No isolated failure of the existing complete-graph algorithm was observed. |
| Empty/value-only/restricted/permission/scope/queryability controls | Ten controls pass, including narrow columns and negation evidence | Fixture evidence only; broader recall must preserve these boundaries. |
| Service-account count | `service_account` present; active-human concept and metric also present as context | Extra candidates are not selected definitions. Broad context can contain tempting but inappropriate choices; no precision or model-error claim follows. |

All 22 explicitly labeled canonical cases (11 vocabulary, eight definition,
three relationship) have complete expected context. This is useful counter-evidence
against attributing all semantic failures to retrieval. Once adequate context is
available, interpretation and supported algebra remain separate suspects.

## Mechanisms and competing hypotheses

**High confidence: hard candidate omissions are deterministic and upstream of
the provider.** [`semantic_grounding.py`](../../../backend/app/query_engine/semantic_grounding.py)
uses normalized contiguous reference spans (around lines 196–240 and 1734–1824).
Normalization has a finite singularization list; it is not semantic retrieval.
Description fallback requires a unique score of at least two and runs only when
no direct entity/concept/metric/rule anchors exist (around lines 296–306,
980–1008). Changing model/reasoning/token settings cannot make an absent entity
legal under the unchanged candidate subset validator.

**High confidence: entity/path coverage and definition coverage differ.**
Concepts and metrics are selected for anchor entities before connector-path
entities are appended (around lines 340–433). Rules are selected only from their
reference matches. The expanded review contrast therefore has broad entity
coverage but missing business definitions. This is consistent with the documented
ownership boundary, not evidence that relationship completeness should be removed.

**Unproven: retrieval is the dominant cause of real user or historical provider
failures.** This probe deliberately stresses vocabulary and does not observe a
provider. Definitions may also be expressed by authorized literal filters, and a
model can correctly clarify ambiguous inputs. Conversely, present definitions do
not ensure correct composition. The stronger-model hypothesis is still open for
cases with complete context; it is not a remedy for the hard entity subset gate.

## Offline alternatives and byte budget

The current cap is **16,000 bytes**, not 20KB or 16KiB. The global authorized
catalog contains 11 entities, 19 relationships, 34 concepts, one metric, and two
rules. A complete authorized projection serialized with the **production
projection helpers** is **18,366 bytes even after omitting examples, candidate
signals, and suggested intent**. Expose-all facts does not fit unchanged.

After observing the primary results, the probe performs three **copy-only,
post-first-run inventories** in memory. These do not modify production, rerank
signals, run trimming, validate a new algorithm, or measure provider behavior.

| Offline copy alternative | Cases with all expected IDs | Cases fitting cap | Complete and fitting |
| --- | ---: | ---: | ---: |
| Full authorized facts, minimal | 69/69 by construction | 0/69 | 0/69 |
| All authorized entities/relationships, keep current definitions | 60/69 | 69/69; 7,064–14,521 bytes | 60/69 |
| Add definitions for selected/connector entities and rules whose definitions are available | 42/69 | 55/69; max 20,655 bytes | 28/69 |

The second alternative isolates how much entity/relationship omission alone
costs in this corpus, but leaves nine definition cases incomplete and adds
unmeasured ambiguity. The third demonstrates why naive connector-definition
closure is not a safe drop-in: it overflows 14 cases, including previously covered
canonical inputs. Applying the existing optional-definition trimming could remove
the newly added context again; that outcome is not silently counted as fixed.

## Narrow W6b decision and acceptance ideas

Within this component, the correction candidate is **bounded authorized candidate/context
coverage**, with two explicit concerns: ordinary entity vocabulary across more
than one domain family, and relevant business definitions for multi-entity
requests. The consolidated [Hebrew report](../2026-11-01-w6a-semantic-diagnosis-he.md) prioritizes the independently reproduced output-identity defect before this component proposal. Two noun aliases alone would repair two examples but leave the broader
failure mechanism demonstrated here. A glossary-only change is the smaller option
if the owner explicitly chooses a narrowly documented vocabulary contract;
it should not be presented as a general recall solution.

Compare a catalog-owned vocabulary correction against bounded entity/relationship
fallback and selective definition inclusion, preserving the current cap,
permission projection, one-call planner ownership, dependency closure and
non-binding lexical hints. The inventory does not select a winning retrieval
algorithm. Broad expose-all definitions, embeddings, an extra provider call, or a
larger model are not justified as first steps by this evidence. Existing provider
instructions already assign interpretation/OR ownership; repeating that generic
instruction has no demonstrated incremental value here.

Before accepting W6b, require explicit supported-vocabulary judgments for ambiguous
phrases; unchanged canonical and negative-control behavior; target entity coverage
and named-definition coverage reported separately; cap/dependency closure under
multi-anchor graphs; and targeted checks showing copied connector context does not
become a mandatory filter. Independently author unseen paraphrase/contrast
families **after** fixing the scope and before tuning; keep them unavailable to the
implementer until validation. For laptop-like subtypes, test the actual authorized
filter and result meaning separately from entity recall. A bounded provider
experiment, if separately authorized, must compare the same frozen cases and
context under an exact model/call budget and report retrieval, selection, and
final correctness as separate stages.

Ruff and the probe self-checks pass; repeated output is deterministic. Production
source is unchanged. PostgreSQL/API/provider behavior and independent held-out
quality were not checked. No semantic fix or release qualification is claimed.
