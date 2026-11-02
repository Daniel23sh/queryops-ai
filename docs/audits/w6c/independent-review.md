# Independent W6c offline methodology review

A fresh-context reviewer inspected the complete evidence branch relative to
runtime baseline `92bf4ca8b7df1d591cdb1b5f3e66188e19cdb5f0`, the connected
runtime/evaluator contracts and all new audit artifacts. The reviewer did not
author the W6b implementation, frozen corpus, manual witnesses or harness.

**Verdict: approved for an unmerged offline evidence PR. No blocking finding remains.**
This is an evidence/methodology approval, not semantic product readiness or live
provider qualification.

## Reproduction and closed issue

The reviewer ran `selfcheck.py` (three negative guards) and the corrected
`probe.py --out /tmp/w6c-independent-replay.json` from `backend/`, with
`PYTHONPATH=.` and the explicit disposable PostgreSQL variables documented in
[the report](../2026-11-02-w6c-offline-validation-he.md). It used the existing
isolated `127.0.0.1:55469/queryops_w6c_test`; no initialization, reseed or reset.

Replay covered 20 case records, 19 projections, 14 manual positive witnesses,
30 variants (28 accepted), and eight join assignments. Every stable observation
matches `results.json` after removing transaction time/snapshot only. The frozen
question, witness, fixture and manifest bytes match their freeze commits.
Canonical JSON SHA256 of that stable comparison payload:
`8c4b50a49b6758e82ebf730de03c2f5318853e605536bb4b7dbe9c1712324362`.

The reviewer found an audit-harness guard issue: frozen Python modules were
imported before hash checks. The parent moved those imports after frozen-input,
runtime-source and dataset/catalog checks. The reviewer inspected the correction,
reran three selfchecks and the full probe, and closed the issue. The oracles,
fixture and product were not changed. Selfcheck now also asserts that artifact
imports are not reached on a mismatched frozen input.

Freeze commits occurred at 2026-11-02T09:04:57Z (`e22831e`) and
2026-11-02T09:07:52Z (`97ef82b`); recorded execution occurred afterward. Git
history alone cannot prove the absence of an earlier unrecorded execution.
The question author's no-execution statement and tool history supply the bounded
methodological provenance; they are not cryptographic proof of universal secrecy.

Ruff, Python compilation, local Markdown targets and diff whitespace checks
passed in the review. A wording clarification was incorporated: W6C-016 exercises
projection with an unresolved flag only, not plan validation or clarification
selection under that flag.

## Limits retained

- F1 exhausts the selected tree's join assignments; it does not prove every
  possible graph encoding impossible.
- F2 is fixture discrimination failure, not a proven result-comparator false
  positive. The extra-filter oracle remains frozen and its failure is disclosed.
- Scope/resource/column observations are bounded synthetic contexts. Existing
  264/292 regression results were inspected but not independently rerun by this
  reviewer.
- The live proposal is unexecuted and requires explicit model/configuration/
  question/budget approval plus a verified physical-dispatch guard before use.
- Provider interpretation, natural-language answer accuracy, model availability,
  live usage/cost and V1 release qualification remain unmeasured.

No product, source/oracle edits, paid requests, reset or merge were performed by
the reviewer.
