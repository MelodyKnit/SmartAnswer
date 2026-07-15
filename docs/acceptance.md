# Acceptance Workflow

Updated: `2026-06-07`

## 1. Purpose

The acceptance workflow gives the project one command that verifies the implemented local service stack is still coherent.

It checks:

- unit tests
- normalized exports for CMMLU, AGIEval MCQ, and the combined verified index
- OCS-style config shape
- config-driven client simulation and handler evaluation
- local query API
- runtime status endpoint
- OCS-style compatibility API
- served OCS-style config endpoint
- CORS preflight
- mock OpenAI-compatible model fallback

## 2. Command

Run:

```powershell
python scripts\run_acceptance.py --index data\normalized\cmmlu.jsonl
```

## 3. Report

The consolidated report is written to:

```text
data\manifests\acceptance-report.json
```

## 4. What Passing Means

Passing acceptance proves:

- the normalized CMMLU index can be queried
- the broader verified index can be regenerated
- `/query` works through GET and POST
- `/status` reports the loaded index and non-sensitive model switches
- `/ocs/query` returns the configured `code/data/ai` shape
- `/api/v1/configs/ocs-local-study-bank.json` returns the expected source config
- the local config file has the expected source fields
- the local config can be used to call the source URL and execute the handler
- model fallback works through a local OpenAI-compatible mock provider

## 5. What Passing Does Not Prove

Passing acceptance does not prove:

- a real local model runtime is installed
- a real external client has loaded the config
- third-party benchmark datasets are redistributable beyond their documented licenses

These remain external-environment checks.

