# Architecture

Updated: `2026-06-07`

## 1. Objective

This project needs a reliable study-oriented retrieval service that accepts normalized question input, searches a maintained question bank, optionally asks a large model to normalize or explain the answer, and returns a source-backed result that can be reviewed by a user.

## 2. Design Principles

- retrieval first, generation second
- stable normalized API before client-specific adapters
- source attribution on every answer path
- pluggable model providers
- pluggable data ingestion pipelines
- narrow, testable service boundaries

## 3. Recommended High-Level Architecture

```text
Question Input
  -> Input Normalizer
  -> Retrieval Facade
     -> Exact/keyword matcher
     -> Vector/hybrid retriever
     -> External source adapter (optional and gated)
  -> Evidence Ranker
  -> Answer Composer
     -> direct answer resolver
     -> LLM explanation strategy
     -> trusted LLM Answer Cache
  -> Response Formatter
  -> HTTP API
```

## 4. Main Components

### 4.1 Input Normalizer

Responsibility:

- validate incoming payload
- normalize question text
- normalize option lists and question type
- generate a canonical retrieval query

Inputs:

- title
- options
- type
- optional metadata such as subject, source, tags, locale

Outputs:

- normalized question payload
- canonical search keys
- validation errors when required fields are missing

### 4.2 Retrieval Facade

Responsibility:

- expose one internal retrieval entry point
- hide whether the answer came from exact match, hybrid RAG, or an optional external source

Suggested pattern:

- `Facade` for a single stable service boundary
- `Strategy` for interchangeable retrieval methods
- `Adapter` for external systems with mismatched APIs

Sub-capabilities:

- exact title match
- fuzzy title match
- option-aware reranking
- vector search against chunked knowledge
- optional external-source lookup with clear provenance

### 4.3 Evidence Ranker

Responsibility:

- score candidate evidence
- prefer curated question-bank entries over weak model-only guesses
- consider title similarity, option overlap, question-type compatibility, and source confidence

Suggested scoring order:

1. curated QA exact match
2. curated QA fuzzy match with option support
3. trusted RAG snippet with strong overlap
4. trusted AI cache entry promoted after repeated agreement
5. external source result with verifiable provenance
6. model-only fallback

### 4.4 Answer Composer

Responsibility:

- decide whether an answer can be returned directly from evidence
- reuse only trusted cached AI answers when local evidence misses
- ask the LLM only when normalization, explanation, or disambiguation is needed
- force structured output

Output expectations:

- candidate answer
- explanation
- source list
- confidence
- resolution mode such as `exact_match`, `retrieval_match`, `llm_normalized`, or `fallback`

### 4.5 Response Formatter

Responsibility:

- map internal response into a stable external JSON contract
- preserve both machine-friendly fields and human review fields

## 5. Provider Abstraction

The model layer should not be coupled to any single runtime.

Recommended provider contract:

- `chat(messages, options) -> structured result`
- `embed(texts) -> vectors`
- `health() -> provider status`

Recommended provider implementations:

- OpenAI-compatible cloud API
- Ollama
- LM Studio
- vLLM

Why this matters:

- the project can start on cloud APIs and later switch to local inference with minimal code churn
- MaxKB and FastGPT both work well when the backing model endpoint is OpenAI-compatible

## 6. Data Storage Model

### 6.1 Canonical Question Record

Fields to preserve:

- `question_id`
- `title_raw`
- `title_normalized`
- `question_type`
- `options_raw`
- `options_normalized`
- `answer_raw`
- `answer_normalized`
- `explanation`
- `subject`
- `chapter`
- `tags`
- `source_name`
- `source_url`
- `source_license`
- `ingest_batch`
- `created_at`
- `updated_at`

### 6.2 Retrieval Index Views

Maintain separate views for:

- exact-match text index
- fuzzy/keyword index
- vector index
- provenance and license metadata

## 7. Implemented Initial Stack

Current implementation:

- backend: FastAPI service served by uvicorn
- index: normalized local JSONL files under `data\normalized`
- retrieval: exact match first, fuzzy match second
- model provider: OpenAI-compatible chat completions adapter
- AI learned bank: unified JSONL learned-bank under `data\normalized\ai-learned.jsonl`, promoted only after repeated high-confidence agreement
- external client adapter: OCS-style `/ocs/query` response and source config

Current implemented runtime flow:

```text
local exact match
  -> direct answer rules
  -> trusted AI learned-bank match
  -> local fuzzy match
  -> model fallback
     -> optional web search before model answer
     -> evidence-backed model answer when search succeeds
     -> plain model answer when search has no evidence
```

This is the current baseline behavior. It should not be confused with a stricter future policy such as `model first, then search only on uncertainty`, because that flow is not yet implemented.

Why this is the right first stack:

- it directly matches the required OCS configuration workflow
- it avoids putting model API keys in browser-side configuration
- it works with both cloud APIs and local model runtimes
- it keeps source attribution and review metadata attached to every answer path

## 8. Optional Future Product Stack

### Option A: faster product-led route

- application layer: `MaxKB`
- model endpoint: cloud OpenAI-compatible API first
- later local swap: `Ollama` or `vLLM`
- seed data: curated QA CSV/XLSX

Why:

- knowledge base management and app API already exist
- supports offline files, tables, QA pairs, and website knowledge sources
- supports OpenAI-compatible application API

### Option B: more engineering-led route

- backend: Python service
- storage: PostgreSQL + pgvector
- embedding/rerank/model: OpenAI-compatible providers
- ingestion: CSV/XLSX/JSON pipeline

Why:

- highest long-term control
- best if custom scoring and custom exports matter more than admin UI

## 9. Reliability Controls

The service should not return a plain answer without provenance metadata.

Minimum controls:

- confidence score
- source list
- resolution mode
- retrieval trace id
- ingest batch id
- health checks for model and retrieval dependencies

Recommended operator checks:

- source license recorded during import
- duplicate detection during ingestion
- schema validation for imports
- explicit fallback labels when the model is guessing

## 10. What Should Not Be Coupled Early

Do not hard-couple:

- client adapter logic with core retrieval logic
- one-off external source parsers with canonical storage schema
- model prompts with transport-layer request handling
- local-only runtime assumptions with the provider interface

## 11. Development Readiness

The core implementation is in place. Further development should focus on:

- real OCS client validation
- real cloud or local model endpoint validation
- additional licensed source ingestion
- stronger retrieval with option-aware scoring or vector search if needed

