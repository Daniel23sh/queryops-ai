# Terra configuration migration — 2026-11-03

Environment is authoritative for operator values. `provider_config.py` owns typed
validation, bounds and safe fallback defaults; Compose only forwards values.
Mock remains the implicit provider. An API key alone cannot enable OpenAI.
Conflicting explicit CLI/environment models are rejected. Normal retries remain
2; W6c diagnostic retries are 0 in its separately versioned contract.

The local ignored `.env` was checked using only the six non-secret provider
settings: its model was already `gpt-6.1-terra`, low/2048/45/2. No secret or
unrelated value needed changing. `.env` must never be staged.

## Old-model inventory and decisions

The complete repository text search included tracked and ignored source, scripts,
templates, CI, planning and tests, excluding Git objects, installed dependencies,
bytecode, generated bundles and test caches. Secrets were not printed. All Terra
occurrences were classified before migration; no Luna identifier was converted.

| Occurrences at baseline | Decision |
| --- | --- |
| `provider_config.py`, `.env.example`, README setup | Migrate active Terra defaults/examples to `gpt-6.1-terra` |
| `docker-compose.yml` | Remove five duplicate OpenAI defaults; forward environment values |
| `test_provider_config`, `test_openai_provider`, `test_llm_provider`, `test_query_engine_service`, `test_evaluation_cli`, `test_evaluation_runner`, `test_evaluation_api`, `test_evaluation_stability`, `test_v1_readiness`, `test_v1_readiness_cli` | Migrate synthetic Terra candidate fixtures/assertions to current candidate; these are tests, not recorded live results |
| Frontend `appTestUtils.tsx`, `EvaluationPage.test.tsx` | Migrate synthetic current-candidate labels |
| Luna identifiers in environment/provider drift, stability/readiness mismatch and unsafe-provider fixtures | Preserve intentional alternate-model behavior; never substitute an unrelated variant |
| New provider-config negative cases using old Terra | Preserve intentionally: current runtime must reject historical model identity/conflicting override |
| `docs/audits/2026-10-26-project-audit-he.md`, `2026-11-01-w6a-semantic-diagnosis-he.md`, `2026-11-02-w6c-offline-validation-he.md` | Preserve actual past configuration, commands, outcomes and proposals |
| `docs/audits/w6a/{baseline.json,composition-findings.md,independent-review.md}` | Preserve immutable historical evidence |
| `docs/audits/w6c/live-experiment-proposal.md` | Preserve original proposal; successor configuration is separately versioned |
| `docs/development/m10-completion-roadmap.md` | Preserve recorded Luna canary result |
| `.pytest_cache` / `backend/.pytest_cache` | Generated test-name history; not operating configuration, never committed |
| Local `.env` | Already target; preserved secrets and normal retries |

No old-model references occurred in active scripts, CI configuration, frozen V2
dataset/catalog inputs or ignored planning specifications. Future old-model
mentions in this inventory explain historical decisions rather than select a
runtime model.

## Compatibility evidence

On 2026-11-03, official [GPT-6.1 Terra documentation](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
listed exact API ID `gpt-6.1-terra`, Responses, Structured Outputs and reasoning
`low`. This establishes documented API compatibility, not this account's access
or semantic accuracy. No model-list probe or billable request was made. Existing
single structured SemanticPlan, prompt, catalog, renderer and conformance remain
unchanged. Historical live evidence is invalid for this new candidate identity.
