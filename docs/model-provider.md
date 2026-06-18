# Model Provider

Updated: `2026-06-07`

## 1. Purpose

The project supports an optional OpenAI-compatible model provider. Local retrieval remains the first source of truth. The model layer is only used when explicitly enabled at startup.

This provider can point to either:

- a cloud API that exposes OpenAI-compatible `/chat/completions`
- a local runtime such as Ollama, LM Studio, or vLLM
- a self-hosted gateway that normalizes model providers behind an OpenAI-compatible API

## 2. Provider Contract

Implementation:

- [llm/providers/base.py](../src/study_qb_assistant/llm/providers/base.py)
- [llm/providers/openai_compatible.py](../src/study_qb_assistant/llm/providers/openai_compatible.py)
- [http_client.py](../src/study_qb_assistant/http_client.py) wraps `httpx` for timeouts, optional proxy support, JSON decoding, and HTTP status errors.

The provider returns:

- `candidate_answer`
- `answer_text`
- `explanation`
- `confidence`

## 3. Environment Variables

Required when model features are enabled:

- `STQB_LLM_BASE_URL`: base URL for an OpenAI-compatible endpoint
- `STQB_LLM_MODEL`: model name

Optional:

- `STQB_LLM_API_KEY`: API key, read only from the environment
- `STQB_LLM_STREAM`: defaults to `true`; keep enabled for gateways that return Server-Sent Events chunks
- `STQB_LLM_MAX_COMPLETION_TOKENS`: defaults to `700`
- `STQB_WEB_SEARCH_PROVIDER`: comma-separated search providers; defaults to `duckduckgo`, set to `none` to disable
- `STQB_GOOGLE_SEARCH_API_KEY` and `STQB_GOOGLE_SEARCH_CX`: Google Programmable Search JSON API credentials
- `STQB_BAIDU_SEARCH_API_KEY`: Baidu Qianfan AI Search API key
- `STQB_SEARCH_PROXY`: optional HTTP/HTTPS proxy for web-search requests, for example `http://127.0.0.1:7890`
- `STQB_LLM_PROXY`: optional HTTP/HTTPS proxy for model provider requests
- `STQB_LLM_CACHE_ENABLED`: defaults to `true`; persist high-confidence AI answers only after repeated agreement
- `STQB_LLM_CACHE_MIN_CONFIDENCE`: defaults to `0.95`
- `STQB_LLM_CACHE_MIN_CONFIRMATIONS`: defaults to `2`
- `STQB_ANSWER_RULES_PATH`: optional curated fixed-expression rule file; not enabled by default

No API key should be written into project files.

## 4. Startup Modes

Local retrieval only:

```powershell
python scripts\serve_local.py --index data\normalized\cmmlu.jsonl
```

Use the model only when local lookup misses:

```powershell
python scripts\serve_local.py --index data\normalized\cmmlu.jsonl --llm-fallback
```

Use the model to add explanations to local matches that lack explanations:

```powershell
python scripts\serve_local.py --index data\normalized\cmmlu.jsonl --llm-explain
```

Use both:

```powershell
python scripts\serve_local.py --index data\normalized\cmmlu.jsonl --llm-fallback --llm-explain
```

## 5. Cloud API Example

Use this mode when answer quality and low local hardware usage matter more than offline inference. The configured endpoint must expose an OpenAI-compatible `/chat/completions` API.

```powershell
$env:STQB_LLM_BASE_URL="https://api.example.com/v1"
$env:STQB_LLM_MODEL="your-model-name"
$env:STQB_LLM_API_KEY="your-api-key"
python scripts\serve_local.py --index data\normalized\verified.jsonl --llm-fallback --llm-explain
```

Keep the API key only in environment variables. Do not place it in OCS config, JSON files, examples, logs, or source code.

ClassBot/New API style gateways are handled through the OpenAI-compatible Chat Completions contract. This provider sends `stream: true` by default and joins Server-Sent Events `choices[].delta.content` chunks into the normal message content shape before parsing the answer.

Verify the configured model provider after setting the environment variables:

```powershell
python scripts\verify_configured_model.py
```

The verifier writes a report to `data\manifests\configured-model-verification.json` and does not print the API key.

## 6. Optional Web Search Augmentation

For questions where model memory may hallucinate, the service can search first and pass snippets to the model as evidence. The default provider is DuckDuckGo Instant Answer, which does not require a project API key.

Current implemented behavior:

- web search is only reached after local retrieval, direct rules, trusted AI learned-bank lookup, and fuzzy retrieval all miss
- once the request enters model fallback, the `SearchAugmentedModelProvider` searches before asking the model
- if search returns evidence, the evidence is passed into the model prompt
- if search returns no evidence, or the search provider is cooling down after recent failures, the provider falls back to a plain model answer
- the current implementation does not yet perform a second forced search only because the model reported low confidence

Default keyless mode:

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="duckduckgo"
```

Disable web search completely:

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="none"
```

Use a local proxy for search engines:

```powershell
$env:STQB_SEARCH_PROXY="http://127.0.0.1:7890"
```

Use a proxy for the model API if needed:

```powershell
$env:STQB_LLM_PROXY="http://127.0.0.1:7890"
```

Google example:

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="google"
$env:STQB_GOOGLE_SEARCH_API_KEY="your-google-api-key"
$env:STQB_GOOGLE_SEARCH_CX="your-programmable-search-engine-id"
```

Baidu example:

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="baidu"
$env:STQB_BAIDU_SEARCH_API_KEY="your-baidu-ai-search-api-key"
```

Both can be enabled:

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="google,baidu"
```

Search keys are read only from environment variables. The project intentionally uses official API-style providers instead of scraping search-result pages.

## 7. AI Learned Question Bank

The service can persist AI-generated answers as normal question-bank JSONL records for repeated OCS requests, but it does not trust a first model answer immediately.

Default behavior:

- first high-confidence model answer is stored as `pending`
- the same normalized question and options must receive the same answer at least `2` times
- only then is the AI learned-bank entry promoted to `trusted`
- only `trusted` entries are loaded into the local retrieval flow as `resolution_mode: ai_cache`
- conflicting model answers are marked `conflict` and are not served from the learned bank

Disable AI answer learning:

```powershell
$env:STQB_LLM_CACHE_ENABLED="false"
```

Tighten promotion:

```powershell
$env:STQB_LLM_CACHE_MIN_CONFIDENCE="0.98"
$env:STQB_LLM_CACHE_MIN_CONFIRMATIONS="3"
```

The default learned-bank path is `data\normalized\ai-learned.jsonl`. Each row is a `CanonicalQuestionRecord` with `source_name: AIGenerated`, `ai_generated` and `auto_learned` tags, and AI status metadata. Legacy `data\runtime\ai-answer-cache.json` entries are migrated into this JSONL format when the model-backed learning path is enabled.

## 8. Curated Answer Rules

Fixed course formulas may be kept data-driven instead of added as Python branches. This mechanism is disabled unless `STQB_ANSWER_RULES_PATH` is explicitly configured.

Each `option_rules` item contains:

- `needles`: text fragments that must all appear in the question title
- `answers`: expected answer texts matched against the current OCS options

This rule file is a seed pack for high-confidence, stable textbook or policy formulas only. It is not the normal way to handle new live questions. New live answers should go through the AI learned-bank confirmation flow, where repeated high-confidence agreement promotes an answer to trusted local retrieval without changing code or patching this JSON file.

Use a different rule file:

```powershell
$env:STQB_ANSWER_RULES_PATH="configs\\my-answer-rules.json"
```

## 9. Reliability Rules

- Local exact or fuzzy matches are preferred over model output.
- Local fixed-expression rules are preferred over model output.
- Trusted AI learned-bank entries are part of local retrieval and carry `AIGenerated` source tags.
- Model fallback responses are marked as `resolution_mode: llm_fallback`.
- Model fallback responses set `review_required: true`.
- Model fallback responses can still be returned even when confidence is low; low confidence currently affects review and AI-bank promotion, not whether an OCS-compatible answer payload is emitted.
- AI learned-bank responses are marked as `resolution_mode: ai_cache`.
- Provider failures return a structured `MODEL_ERROR` response.
- API keys are read from admin model/search configuration first, with environment variables as deployment-level fallbacks; frontend config responses expose only `*_configured` flags, not plaintext secrets.
- When search is configured, search snippets are logged for local troubleshooting, but search credentials are redacted.

## 10. Verified Real Provider

The OpenAI-compatible provider path was live-tested with a private provider. Commit-ready examples should use placeholders:

- base URL: `https://api.example.com/v1`
- model: `your-model-name`
- endpoint: `/chat/completions`
- response mode: streaming Server-Sent Events

The verifier passed and wrote its non-sensitive result to `data\manifests\configured-model-verification.json`.

## 11. Mock Provider Verification

Run:

```powershell
python scripts\verify_model_provider.py --index data\normalized\cmmlu.jsonl
```

The verifier starts:

- a local OpenAI-compatible mock endpoint
- the local study service with `--llm-fallback`

It then checks:

- `/query` returns `resolution_mode: llm_fallback` for a question missing from the local index
- `/ocs/query` preserves `llm_fallback` and `review_required` in `data.ai`

The report is written to:

```text
data\manifests\model-provider-verification.json
```

## 12. Real Local Model Notes

This session checked `http://127.0.0.1:11434/api/tags`, but no Ollama-compatible service was running on that port.

For Ollama-style OpenAI-compatible serving, the expected configuration is:

```powershell
$env:STQB_LLM_BASE_URL="http://127.0.0.1:11434/v1"
$env:STQB_LLM_MODEL="qwen2.5:7b"
python scripts\serve_local.py --index data\normalized\cmmlu.jsonl --llm-fallback --llm-explain
```

The actual model name should match a model installed in the local runtime.

