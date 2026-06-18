# Environment Setup

Updated: `2026-06-07`

## 1. Toolchain Decision

This project uses `Conda` as the project-level Python environment manager.

Reason:

- required by the workspace rules for Python projects
- sufficient for the current lightweight FastAPI service
- keeps runtime dependencies explicit at the project level

## 2. Environment File

Primary file:

- [environment.yml](../environment.yml)

## 3. Bootstrap Commands

Create the environment:

```powershell
conda env create -f environment.yml
```

Activate it:

```powershell
conda activate ai-study-qb
```

## 4. Current Validation Command

Run the current sample-based tests:

```powershell
python -m pytest tests -q
```

Current verified environment:

- Conda environment: `ai-study-qb`
- final validation was run from the `ai-study-qb` environment
- latest result: `61` unit tests passed, FastAPI local service verification passed, and mock model fallback verification passed

## 5. Runtime Dependencies

Current intentionally added runtime/test dependencies:

- `fastapi`: mature route handling, request validation, and ASGI integration
- `httpx`: mature synchronous HTTP client for model/search requests, proxy support, timeouts, and status errors
- `python-dotenv`: robust `.env.local` parsing while preserving existing process variables
- `uvicorn`: ASGI runtime for the local service
- `pytest`: project test runner

## 6. Future Dependency Policy

When new dependencies are added:

- update `environment.yml`
- keep the dependency list minimal
- document why each new dependency is needed

## 7. Model Provider Environment

Optional model-backed service mode reads:

- `STQB_LLM_BASE_URL`
- `STQB_LLM_MODEL`
- `STQB_LLM_API_KEY`
- `STQB_LLM_PROXY`
- `STQB_WEB_SEARCH_PROVIDER`
- `STQB_SEARCH_PROXY`
- `STQB_LLM_CACHE_ENABLED`
- `STQB_LLM_CACHE_MIN_CONFIDENCE`
- `STQB_LLM_CACHE_MIN_CONFIRMATIONS`

API keys are intentionally not stored in project files. The default AI learned-bank path is `data\normalized\ai-learned.jsonl`; it stores AI-generated answers as normal `CanonicalQuestionRecord` JSONL rows with `ai_generated` and `auto_learned` tags. Legacy `data\runtime\ai-answer-cache.json` files are read as a compatibility migration source when model-backed learning is enabled.

