# Delivery Status

Updated: `2026-06-07`

## 1. Completed Capabilities

- Project workspace and rules are established.
- Public source research is documented.
- Public benchmark repositories were downloaded into local raw data.
- CMMLU was normalized into `data\normalized\cmmlu.jsonl`.
- AGIEval MCQ was normalized into `data\normalized\agieval-mcq.jsonl`.
- CMMLU and AGIEval MCQ were combined into `data\normalized\verified.jsonl`.
- Local query API is implemented.
- Runtime status endpoint is implemented.
- OCS-style compatibility endpoint is implemented.
- OCS-style config can be loaded from a local file or served by the running service.
- OpenAI-compatible model provider abstraction is implemented.
- Model fallback and explanation orchestration are implemented.
- OpenAI-compatible provider wiring was verified with a private test provider; commit-ready examples use a placeholder base URL.
- Streaming Chat Completions responses are parsed into OCS-compatible answers.
- End-to-end local service verification is implemented.
- Already-running service verification is implemented.
- Config-driven client simulation is implemented.
- End-to-end mock model fallback verification is implemented.
- Conda environment `ai-study-qb` was created and used for final validation.

## 2. Current Verified Artifacts

- Normalized CMMLU export: `11917` records
- Combined verified export: `18071` records
- Local OCS-style config: [configs/ocs-local-study-bank.json](../configs/ocs-local-study-bank.json)
- Local service verification report: [data/manifests/local-service-verification.json](../data/manifests/local-service-verification.json)
- Model fallback verification report: [data/manifests/model-provider-verification.json](../data/manifests/model-provider-verification.json)
- Config-driven client verification report: [data/manifests/config-client-verification.json](../data/manifests/config-client-verification.json)
- Acceptance report: [data/manifests/acceptance-report.json](../data/manifests/acceptance-report.json)
- Export verification report: [data/manifests/export-verification.json](../data/manifests/export-verification.json)
- Running service verification report: [data/manifests/running-service-verification.json](../data/manifests/running-service-verification.json)

## 3. Verified Commands

Run unit tests:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Verify local query and OCS-style endpoint:

```powershell
python scripts\verify_local_service.py --index data\normalized\cmmlu.jsonl
```

Verify model fallback through a mock OpenAI-compatible endpoint:

```powershell
python scripts\verify_model_provider.py --index data\normalized\cmmlu.jsonl
```

Verify config-driven client behavior:

```powershell
python scripts\verify_config_client.py --index data\normalized\cmmlu.jsonl
```

Verify the already-running final service:

```powershell
python scripts\verify_running_service.py --base-url http://127.0.0.1:8765
```

Run full acceptance:

```powershell
python scripts\run_acceptance.py --index data\normalized\cmmlu.jsonl
```

Latest validation result:

- `6` acceptance groups passed
- `20` unit tests passed
- export verifier passed `3` checks
- local service verifier passed `9` checks
- config-driven client verifier passed `4` checks
- mock model provider verifier passed `5` checks
- running service verifier passed `6` checks
- real configured ClassBot model verifier passed `2` checks

Start the local service:

```powershell
python scripts\serve_local.py --index data\normalized\verified.jsonl --host 127.0.0.1 --port 8765
```

## 4. Remaining Real-Environment Checks

These are the only major checks not proven in this environment:

- A real local model endpoint was not running at `127.0.0.1:11434`.
- A real OCS client session has not been used to call `configs/ocs-local-study-bank.json`.
- M3KE license terms still need manual confirmation before broader redistribution.
- C-Eval full data payload still needs a reachable download path.

## 5. Recommended Next Real Check

For a cloud OpenAI-compatible model API, use:

```powershell
$env:STQB_LLM_BASE_URL="https://api.example.com/v1"
$env:STQB_LLM_MODEL="your-model-name"
$env:STQB_LLM_API_KEY="your-api-key"
python scripts\serve_local.py --index data\normalized\verified.jsonl --llm-fallback --llm-explain
```

Then verify the configured provider with:

```powershell
python scripts\verify_configured_model.py
```

For ClassBot, keep `STQB_LLM_MODEL` as `gpt-5.4` including the hyphen. The provider defaults to streaming mode because this gateway returns Chat Completions chunks for that model.

For a local OpenAI-compatible model service, use:

```powershell
$env:STQB_LLM_BASE_URL="http://127.0.0.1:11434/v1"
$env:STQB_LLM_MODEL="your-local-model-name"
python scripts\serve_local.py --index data\normalized\cmmlu.jsonl --llm-fallback --llm-explain
```

Then query an intentionally missing question through `/ocs/query` and confirm:

- `data.ai.resolution_mode` is `llm_fallback`
- `data.ai.review_required` is `true`
- `data.ai.confidence` is present

## 6. Completion Assessment

The software foundation is ready for local use and further development. The only unproven pieces are external-runtime checks that require the user's actual local model service and real client environment.

