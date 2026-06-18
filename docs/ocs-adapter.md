# OCS-Style Adapter

Updated: `2026-06-07`

## 1. Purpose

The local service exposes `/ocs/query` as a thin compatibility endpoint around the stable internal `/query` API.

Use it for local study and review workflows where an external client expects a compact `code/data` response shape.

## 2. Endpoint

```text
http://127.0.0.1:8765/ocs/query
```

Supported methods:

- `GET`
- `POST`

## 3. Config Artifact

Local config file:

- [configs/ocs-local-study-bank.json](../configs/ocs-local-study-bank.json)

When the local service is running, the same source shape is served at:

```text
http://127.0.0.1:8765/configs/ocs-local-study-bank.json
```

Generate config for a custom host or port:

```powershell
python scripts\generate_ocs_config.py --base-url http://127.0.0.1:8765
```

Config content:

```json
[
  {
    "name": "Local Study Question Bank",
    "homepage": "http://127.0.0.1:8765/healthz",
    "url": "http://127.0.0.1:8765/ocs/query",
    "method": "get",
    "type": "GM_xmlhttpRequest",
    "contentType": "json",
    "data": {
      "title": "${title}",
      "options": "${options}",
      "type": "${type}"
    },
    "handler": "return (res)=>res.code === 0 ? [res.data.question, res.data.answer] : [res.message || (res.data && res.data.question) || '未找到答案', undefined]"
  }
]
```

OCS expects the handler return value to place the answer in the second slot. The local config therefore returns `[question, answer]` for successful responses.

OCS/Tampermonkey deployments may also require the script environment to allow connections to the local host, for example `127.0.0.1` or `localhost`. The project service sends permissive CORS headers, but userscript managers can still enforce their own connection allow-list.

## 4. Successful Response Shape

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "question": "壁胸膜的分部不包括",
    "answer": "B",
    "answer_text": "肺胸膜",
    "explanation": null,
    "ai": {
      "review_required": false,
      "confidence": 0.99,
      "resolution_mode": "exact_match",
      "sources": []
    }
  }
}
```

## 5. Error Response Shape

```json
{
  "code": 1,
  "message": "title is required",
  "data": {
    "question": "",
    "answer": null,
    "ai": {
      "review_required": true,
      "confidence": 0.0,
      "resolution_mode": "invalid_request",
      "error_code": "INVALID_REQUEST"
    }
  }
}
```

## 6. Review Boundary

The adapter preserves `review_required`, `confidence`, `resolution_mode`, and `sources` in `data.ai`. External clients should keep that metadata visible where possible, especially for fuzzy or model-only results.

## 7. Verification

Run:

```powershell
python scripts\verify_local_service.py --index data\normalized\cmmlu.jsonl
```

The verifier starts the local service temporarily and checks `/ocs/query` returns `code: 0` and the expected answer for a known local question.

To simulate a config-driven client and evaluate the handler:

```powershell
python scripts\verify_config_client.py --index data\normalized\cmmlu.jsonl
```

The config-driven verifier reads the source config, substitutes `${title}`, `${options}`, and `${type}`, calls the configured URL, and evaluates the configured `handler` with Node.js. This is the closest local automated check to the final OCS usage shape.

