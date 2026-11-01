# W6a independent review

What this change does: it diagnoses candidate availability, business composition,
supported plan encodings, output delivery and evaluator proof without changing
the product. It recommends one deterministic output-identity correction for a
separate W6b decision.

Reviewed on 2026-11-01 by a fresh-context reviewer who authored none of the
investigation. Initial immutable head: `a31eb0d5966576960e88ce1336a743eef859425e`.
Correction and final reviewed head: `b1852b80ed56437444f1293be81576b7a68d1f36`.
Runtime baseline: `b1f03a4790c7569f7da0ef8d9be57ddd6da023c5`.
This review adds only this file; it implements no semantic correction.

## Findings and resolution

Two P2 investigation defects required correction before handoff. Both are resolved
in `b1852b8`; no blocking finding remains.

1. **Algebra replay did not enforce its frozen baseline.** The initial
   [algebra probe](algebra_probe.py) recorded identities but did not compare
   source, dataset or catalog against [the freeze](baseline.json). Changed runtime
   code could therefore be measured under the investigation's claimed baseline.
   The correction checks all three before database endpoint validation,
   initialization or connection. The composition probe's existing checks were
   also moved before initialization. Independent negative checks forced dataset
   mismatch, catalog mismatch and Git-diff failure in each script: all six failed
   before either endpoint validation or `create_engine` was reached.
2. **Algebra replay required an unrelated temporary test log and emitted static
   test-pass metadata.** The initial script always read
   `/tmp/queryops-w6a/algebra-relational-tests.log` and wrote `33 passed` without
   running those tests. A clean documented replay could fail after doing its
   database work, or repeat a stale test claim. The correction removes that
   dependency and metadata. Actual regression evidence is reported separately.
   Independent replay of the corrected script completed; inspection confirms
   there is no temporary-log read or `focused_regression` result field.

## Independent evidence and judgment

I read the full changed diagnostic scripts, corpus expectations, result artifacts,
component findings, consolidated report and planning diff. I traced the relevant
unchanged grounding, plan validation, renderer, executor, provenance, scoring,
identity proof, provider instructions, V2 contracts and relational tests. I used
the repository instructions, M10 roadmap, validation model and Ponytail review
skill. Review assumes an operator running these dedicated local diagnostics.

| Claim challenged | Independent result | Decision implication |
| --- | --- | --- |
| F14 is an actual upstream restriction | Replayed all 79 cases into a temporary output directory; result bytes match the tracked artifact. The validator rejects entity IDs outside the candidate projection. Canonical paths work; ordinary noun variants can leave no legal entity candidate. | Candidate availability is a real defect boundary. It is separate from provider selection and answer correctness. |
| Candidate failure denominators are meaningful | Recomputed 69 positives and 10 controls: 40/69 fully projected; entity 56/91, concept 30/40, relationship 7/13, rule 3/6 and metric 3/3 occurrences. All expected positive IDs exist and are eligible in the fixture. | The denominators are internally correct. The purposive sample does not estimate population recall; subscriptions, units and entitlements remain interpretation hypotheses. |
| More context is automatically a fix | Copy-only inventory reproduces 18,366 bytes for minimal full facts against the 16,000-byte cap; all-entity/relationship copies cover 60/69 and fit this corpus, while definition closure overflows 14 cases. | This supports comparing bounded candidate alternatives later, not selecting a new retrieval algorithm or assuming improved model behavior. |
| F3 proves a current model failure | Handwritten intended OR returns 16/16. Status-only returns 11/16; OR plus one branch still reports the rule selected while returning 11, 9 or 4. No-DISTINCT returns 25 rows for 16 devices. | These isolate legal-plan failure mechanisms. They do not replay a historical provider payload or measure the current configured model. Existing instructions already distinguish OR rules from extra AND constraints. |
| hard-005 is merely evaluator inconvenience | The fixed V2 contract requests both device and user IDs. Canonical execution returns columns `id,id`, one mapped key and unequal values at the two tuple positions. Provenance rejects `output_name_duplicated`. | Actual information is lost before comparison. Deterministic output identity is the smallest well-supported first correction. FK substitutions pass row-only comparison but fail the unchanged detail contract; relaxing scoring is not a remedy. |
| F11 requires broad algebra expansion | Six canonical aggregate forms pass. hard-004 has one qualifying user on the explicit nonempty fanout fixture; non-distinct COUNT produces two. Hidden redundant grouping is rejected by the encoding contract despite a passing downstream SQL witness. | Supported business answers exist. SQL legality, selected-plan conformance, semantic observation and result comparison are distinct contracts. No broad expansion is justified. |
| Equal sample rows prove general equivalence | Extra dimensions, COUNT fanout, missing projected identity, LEFT-join proof differences and grouped/scalar empty witnesses behave differently across the recorded stages. | The report correctly retains conservative identity and grain checks. SQL witnesses for rejected plans are not accepted product plans. |

The October audit supports the historical 9/10 `gpt-5.6-luna` observation and
`medium-009` omission; it does not establish current-model frequency. I verified
that runtime, frontend, tests, catalog, datasets and tracked evaluation contracts
have no diff from the frozen baseline. The changed files remain diagnostic and
planning artifacts. I found no raw result rows, provider payloads or credentials
in the diagnostic outputs; synthetic fixture identities appear only in code.

## Checks actually run

- Recreated the freeze with `PYTHONPATH=. .venv/bin/python
  ../docs/audits/w6a/freeze_baseline.py`; parsed output equals `baseline.json`.
- Replayed `candidate_probe.main()` after redirecting only its artifact directory
  to `/tmp/queryops-w6a/independent-candidate`, preserving the original source root
  and copying its unchanged corpus/freeze. All 79 cases match byte-for-byte.
- Ran both PostgreSQL probes on the initial and corrected heads, **without**
  `--initialize` or `--add-contrast-fixture`. Used only the existing guarded
  disposable composition database on port 55447 and algebra database on 55448,
  with the required sibling application URL and disposable opt-in. All 18 and 19
  probe records match tracked stage, semantic, result, shape and hash evidence;
  transaction metadata naturally differs. Seed fingerprints match.
- Ran `PYTHONPATH=.:tests .venv/bin/pytest
  tests/test_relational_semantics.py -q -rs` on the algebra cluster: **33 passed,
  zero skipped**. Its temporary-table writes roll back; no fixture reset occurred.
- Independently ran the six pre-database negative guard checks described above.
- Ruff passed for all four diagnostic scripts. `git diff --check` passed;
  baseline runtime diff is empty; no ignored planning files are tracked or staged.

The initial PostgreSQL attempts were denied by the ordinary network sandbox;
the same bounded commands completed after approved sandbox escalation. This was
an execution-environment restriction, not a probe or database failure.

Corrected replay artifacts are temporary review evidence:

| Artifact | SHA-256 |
| --- | --- |
| `/tmp/queryops-w6a/independent-corrected-composition.json` | `56056904d0516048d8b5c52d6f082a963c7d91f52b946eac1061878f49117ea4` |
| `/tmp/queryops-w6a/independent-corrected-algebra.json` | `24581bd2916f661577ee6f78216ea06132c0e89e3f13d62c3b1bb7df19f3ef76` |

## Limits and next decision

All new cases are exploratory. This review is independent, but it does not turn
the already exposed corpus into blind held-out validation. No provider was
invoked, and no current model-selection accuracy or stability was established.
The candidate fixture verifies real projection/policy functions over unpersisted
metadata, not PostgreSQL RLS. The PostgreSQL probes verify their recorded paths,
not a complete security release suite. The independent 33-test run does not
repeat the coordinator's broader 480-test run.

The composition probe pins only a subset of outcomes in assertions. I separately
compared all 18 records, including negative outcomes and collision shape, against
tracked evidence. They are diagnostic evidence now; W6b must turn relevant
failures into focused regressions. The inactive-user NULL branch has no positive
row in the inspected scope. Browser, dashboard and CSV propagation of duplicate
labels is inferred from the shared result contract, not replayed here. Future
SQL-clock changes can alter fixed-seed temporal counts; same-snapshot comparisons
do not freeze the database clock.

Recommend presenting **only deterministic output identity** for the first W6b
approval, with collisions across fields and aggregate labels, stable ordering,
preserved unique-name behavior, governed PostgreSQL comparison, consumer and
saved-SQL compatibility, and fresh independent contrasts. Keep candidate/context
changes and algebra/prompt/model changes as separate decisions. Freeze new
held-out cases and criteria before validation; exposed failures become known
regressions and must not be reused as unseen evidence after tuning.

The consolidated eight-question provider proposal is explicit and bounded to one
model, eight logical calls and at most 24 transport attempts. It correctly remains
an unexecuted diagnostic proposal with unknown retry billing and no qualification
claim. Any later approval must bind the then-current source/runtime and authorized
actor/scope context as well as the exact questions and configuration.

Verdict: the corrected investigation is suitable for an **unmerged diagnostic
PR**. No unresolved blocking review finding remains. W6b and paid experiments
still require separate owner approval; this is not V1 readiness evidence.

Not checked: paid provider behavior, full release suites, browser/CSV replay or
fresh held-out quality. Remaining risk is unmeasured model selection and consumer
compatibility to be verified in an approved correction. Reviewer writes stopped.
