# API Contract

Updated: `2026-06-07`

## 1. Purpose

This document defines the normalized internal API for the study assistant service. It is intentionally client-agnostic so the backend remains stable even if downstream tools or adapters change later.

## 2. Request Shape

### 2.1 Minimal request

```json
{
  "title": "1+2 = ?",
  "options": [
    "A. 1",
    "B. 2",
    "C. 3",
    "D. 4"
  ],
  "type": "single"
}
```

### 2.2 Extended request

```json
{
  "title": "1+2 = ?",
  "options": [
    "A. 1",
    "B. 2",
    "C. 3",
    "D. 4"
  ],
  "type": "single",
  "subject": "math",
  "source_context": "practice_set_a",
  "tags": ["arithmetic", "basic"],
  "locale": "zh-CN",
  "request_id": "demo-001"
}
```

## 3. Normalized Response Shape

```json
{
  "ok": true,
  "request_id": "demo-001",
  "query": {
    "title": "1+2 = ?",
    "type": "single",
    "options": ["A. 1", "B. 2", "C. 3", "D. 4"]
  },
  "result": {
    "candidate_answer": "C",
    "answer_text": "C. 3",
    "explanation": "The sum of 1 and 2 is 3.",
    "confidence": 0.99,
    "resolution_mode": "exact_match",
    "review_required": false
  },
  "sources": [
    {
      "source_name": "seed-curated-bank",
      "source_type": "qa_record",
      "source_id": "math-basic-0001",
      "source_url": null,
      "score": 0.998
    }
  ],
  "debug": {
    "trace_id": "trace-demo-001",
    "retrieval_strategy": "exact_then_hybrid",
    "provider": "local-normalized-jsonl"
  }
}
```

## 4. Error Response Shape

```json
{
  "ok": false,
  "request_id": "demo-001",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "title is required"
  }
}
```

## 5. Field Rules

### Request fields

- `title`: required string
- `options`: optional array of strings; normalize string input into arrays during ingestion if needed
- `type`: required enum; initial values should be `single`, `multiple`, `judgement`, `completion`, `unknown`
- `subject`: optional string
- `source_context`: optional string
- `tags`: optional string array
- `locale`: optional string
- `request_id`: optional string

### Response fields

- `candidate_answer`: normalized symbolic answer such as `A`, `A#C`, `true`, or a completion string
- `answer_text`: answer rendered for human review
- `explanation`: concise rationale or retrieved explanation
- `confidence`: `0.0` to `1.0`
- `resolution_mode`: `exact_match`, `fuzzy_match`, `rag_match`, `external_source`, `llm_normalized`, `fallback`
- `review_required`: boolean

## 6. External Adapter Mapping Notes

The service should support a thin adapter layer that:

- converts incoming placeholders or foreign field names into the normalized request shape
- converts normalized responses into the downstream consumer format

Keep this adapter outside the core retrieval logic.

## 7. API Versioning And Health Endpoints

All business APIs use the canonical `/api/v1` prefix. The only business exception is the
OCS-compatible `/ocs/query` endpoint, whose path remains stable for imported clients.

- `GET /api/v1/healthz`
- `GET /api/v1/version`
- `GET /api/v1/status`
- `GET /api/v1/query?title=...&options=...&type=...`
- `POST /api/v1/query`
- `GET /ocs/query?title=...&options=...&type=...`
- `POST /ocs/query`

OpenAPI UI is available at `/api/docs`; the schema is served from
`/api/v1/openapi.json`. Legacy unversioned business routes remain temporarily callable,
are hidden from OpenAPI, and return `Deprecation: true` plus a successor `Link` header.

Suggested runtime status response:

```json
{
  "llm": {
    "provider": "openai-compatible",
    "healthy": true
  },
  "embedding": {
    "provider": "openai-compatible",
    "healthy": true
  },
  "retrieval": {
    "provider": "local-normalized-jsonl",
    "healthy": true
  }
}
```

## 8. Validation Rules For Version 1

- reject empty `title`
- coerce `options` strings into arrays only in adapter or ingestion layers
- reject unsupported question types unless explicitly mapped to `unknown`
- always return at least one provenance field when `ok` is true
- mark `review_required` as true when confidence is below threshold or when no curated source was used

## 9. Current Local Implementation

The current local implementation is documented in [local-service.md](../docs/local-service.md).

Current behavior:

- normalized JSONL index
- exact match first
- fuzzy match fallback
- optional OpenAI-compatible model fallback
- provenance required for successful responses
- no external model provider required by default

