# External Client Adapter

Updated: `2026-06-07`

## 1. Purpose

This document describes how an external client should call the local study question-bank service. Keep external adapter logic thin so the backend remains testable and reusable.

## 2. Local Endpoint

Default endpoint:

```text
http://127.0.0.1:8765/query
```

Compatibility endpoint:

```text
http://127.0.0.1:8765/ocs/query
```

Supported methods:

- `GET`
- `POST`

## 3. Field Mapping

External clients should map their local fields into:

- `title`: question text
- `options`: array of options, newline-separated string, or `#`-separated string
- `type`: question type
- `request_id`: optional tracing id

## 4. GET Example

```text
http://127.0.0.1:8765/query?title=壁胸膜的分部不包括&type=single
```

With options:

```text
http://127.0.0.1:8765/query?title=...&options=A.xxx#B.xxx#C.xxx#D.xxx&type=single
```

## 5. POST Example

```json
{
  "title": "壁胸膜的分部不包括",
  "options": ["肋胸膜", "肺胸膜", "膈胸膜", "胸膜顶"],
  "type": "single"
}
```

## 6. Response Handling

External clients should use:

- `ok`
- `result.candidate_answer`
- `result.answer_text`
- `result.explanation`
- `result.confidence`
- `result.review_required`
- `sources`

When `review_required` is true, the client should show the answer as a candidate for manual review.

## 7. OCS-Style Source Shape

For local study and review scenarios, the backend is designed to be easy to call from a source configuration with this shape:

```json
{
  "name": "Local Study Question Bank",
  "homepage": "http://127.0.0.1:8765/api/v1/healthz",
  "url": "http://127.0.0.1:8765/ocs/query",
  "method": "get",
  "type": "GM_xmlhttpRequest",
  "contentType": "json",
  "data": {
    "title": "${title}",
    "options": "${options}",
    "type": "${type}"
  }
}
```

The ready-to-use local config artifact is [ocs-local-study-bank.json](../configs/ocs-local-study-bank.json).

When the service is running, it also serves the same source shape at:

```text
http://127.0.0.1:8765/api/v1/configs/ocs-local-study-bank.json
```

To generate the same shape for another host or port:

```powershell
python scripts\generate_ocs_config.py --base-url http://127.0.0.1:8765
```

Adapter logic should preserve `confidence`, `review_required`, and `sources` so the user can see where a result came from.

## 8. Boundary

This project is built as a local study assistant. Client integrations should present source-backed answer candidates for review and should not hide low-confidence or model-only results.

