# Local Service

Updated: `2026-06-07`

## 1. Purpose

The local service exposes a small study-oriented question lookup API over normalized JSONL data. It returns answer candidates with provenance and confidence metadata.

The HTTP layer is implemented with FastAPI and served by uvicorn. Business logic remains in the retrieval, answering, provider, and auth modules so route handling stays thin. It does not require a database. A model provider is optional and disabled by default.

## 2. Current Implemented Answer Workflow

The current runtime workflow is intentionally documented as the behavior that exists today, not as the future ideal flow.

```text
OCS or /query request
  -> local exact match
  -> direct fixed-answer rules
  -> trusted AI learned-bank match
  -> local fuzzy match
  -> model fallback
     -> if web search is configured, search first
     -> if search returns evidence, pass evidence to the model
     -> if search returns no evidence, call the model without evidence
  -> return answer with provenance and review flags
```

Current notes:

- local retrieval remains the first source of truth
- trusted AI learned-bank entries behave like local question-bank records and are searched before fuzzy fallback finishes
- web search is currently part of the model-fallback path, not a second-stage retry that only runs after the model declares uncertainty
- model fallback answers are returned with `resolution_mode: llm_fallback` and `review_required: true`
- low-confidence model answers are not promoted into the AI learned bank unless they satisfy the configured confirmation thresholds
- the current implementation can still return a low-confidence fallback answer to OCS; the review boundary is carried in `data.ai`

This documented workflow is the baseline the project is following right now. If the policy changes later to `local -> model -> uncertain -> forced search retry`, that should be documented as a deliberate behavior change rather than assumed to already exist.

## 3. Export A Normalized Index

Current verified command:

```powershell
python scripts\export_normalized.py --source cmmlu --output data\normalized\cmmlu.jsonl --manifest data\manifests\cmmlu-export.json
```

Verified result on `2026-06-07`:

- output: `data\normalized\cmmlu.jsonl`
- records: `11917`
- source: `CMMLU`

## 4. Start The Local API

```powershell
python scripts\serve_local.py --index data\normalized\verified.jsonl --host 127.0.0.1 --port 8765
```

Windows helper:

```powershell
.\scripts\start_service.ps1
```

Optional model-backed mode:

```powershell
python scripts\serve_local.py --index data\normalized\verified.jsonl --host 127.0.0.1 --port 8765 --llm-fallback --llm-explain
```

Model-backed mode requires the environment variables documented in [model-provider.md](../docs/model-provider.md).

Available endpoints:

- `GET /healthz`
- `GET /auth/session`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/reset-request`
- `POST /auth/reset-confirm`
- `GET /status`
- `GET /query?title=...&options=...&type=...`
- `POST /query`
- `GET /ocs/query?title=...&options=...&type=...`
- `POST /ocs/query`
- `GET /configs/ocs-local-study-bank.json`

## 5. GET Query Shape

Runtime status:

```text
http://127.0.0.1:8765/status
```

The status endpoint reports non-sensitive runtime facts such as loaded record count, source names, source licenses, and model feature switches. It does not expose API keys.

Minimal query:

```text
http://127.0.0.1:8765/query?title=壁胸膜的分部不包括&type=single
```

Options can be passed as a `#`-separated string:

```text
http://127.0.0.1:8765/query?title=...&options=A.xxx#B.xxx#C.xxx#D.xxx&type=single
```

## 6. POST Query Shape

```json
{
  "title": "壁胸膜的分部不包括",
  "options": ["肋胸膜", "肺胸膜", "膈胸膜", "胸膜顶"],
  "type": "single",
  "request_id": "demo-001"
}
```

## 7. Response Shape

The response follows [api-contract.md](../docs/api-contract.md).

Verified sample response:

```json
{
  "ok": true,
  "request_id": null,
  "query": {
    "title": "壁胸膜的分部不包括",
    "type": "single",
    "options": []
  },
  "result": {
    "candidate_answer": "B",
    "answer_text": "肺胸膜",
    "explanation": null,
    "confidence": 0.99,
    "resolution_mode": "exact_match",
    "review_required": false
  },
  "sources": [
    {
      "source_name": "CMMLU",
      "source_type": "qa_record",
      "source_id": "cmmlu:anatomy:dev:0",
      "source_url": "https://github.com/haonan-li/CMMLU",
      "source_license": "CC BY-NC-SA 4.0",
      "score": 0.99
    }
  ],
  "debug": {
    "retrieval_strategy": "exact_then_fuzzy",
    "provider": "local-normalized-jsonl"
  }
}
```

## 8. Adapter Boundary

Any external client should be a thin adapter around this stable local API.

Adapter responsibilities:

- map external field names into `title`, `options`, and `type`
- call the local service
- display answer, confidence, and source metadata for review

Core retrieval logic should stay inside the local service and search modules.

## 9. Current Startup Flags

- `--index`: normalized JSONL path
- `--host`: bind host
- `--port`: bind port
- `--llm-fallback`: use a configured model only when local lookup misses
- `--llm-explain`: use a configured model to explain local matches that lack explanations
- `--require-auth`: require login for data endpoints; `/ocs/query` also supports configured Bearer keys

The script still starts the service with `python scripts\serve_local.py`; internally it now builds the FastAPI app and runs uvicorn.

## 10. Compatibility Endpoint

The `/ocs/query` endpoint wraps the same lookup result into a compact `code/data` response. See [ocs-adapter.md](../docs/ocs-adapter.md).

## 11. End-To-End Verification

Run:

```powershell
python scripts\verify_local_service.py --index data\normalized\cmmlu.jsonl
```

The verifier checks:

- normalized index exists and has records
- `GET /healthz`
- `GET /status`
- `GET /query`
- `POST /query`
- `GET /ocs/query`
- `GET /configs/ocs-local-study-bank.json`
- `OPTIONS /ocs/query`

The report is written to:

```text
data\manifests\local-service-verification.json
```

To verify an already-running service on the final OCS port:

```powershell
python scripts\verify_running_service.py --base-url http://127.0.0.1:8765
```

## 12. Model Fallback Verification

Run:

```powershell
python scripts\verify_model_provider.py --index data\normalized\cmmlu.jsonl
```

This starts a local OpenAI-compatible mock provider and confirms model fallback is correctly exposed through both `/query` and `/ocs/query`.

