# Research Notes

Updated: `2026-06-07`

## 1. Project Framing

Target capability:

- accept a normalized question payload such as `title`, `options`, and `type`
- retrieve matching content from a maintained question bank
- optionally ask a local or self-hosted LLM for answer normalization and explanation
- return candidate answer, explanation, and source for manual review

Preferred outcome:

- a maintainable local service with stable APIs
- reusable question-bank ingestion and indexing
- source-backed answers instead of raw model guesses

Non-goals for this workspace:

- automatic answer submission
- platform bypass work
- dependence on closed third-party answer APIs with unknown stability

## 2. OCS API Notes

Official reference:

- <https://docs.ocsjs.com/docs/other/api/>
- <https://docs.ocsjs.com/docs/work>
- OCS official repo: <https://github.com/ocsjs/ocsjs>

Key interface details from the developer documentation:

- OCS question-bank configuration is an array of source definitions.
- A source definition can include `url`, `method`, `contentType`, `data`, and `handler`.
- `url` and `data` support placeholder substitution.
- Supported documented placeholders include `${title}`, `${type}`, and `${options}`.
- `handler` is used to map a response into the answer shape expected by OCS.
- First-level fields inside `data` can use custom handler-based parsing.
- The docs also mention a full-domain development version for broad cross-domain requests.

Practical implication for this project:

- our future service should expose a clean HTTP interface that can accept normalized question fields
- the service response should be easy to map into an external client handler
- the core value should live in our retrieval and evidence pipeline, not in client-specific glue

## 3. Candidate Open-Source Platforms

### Tier A: strongest current candidates

1. `MaxKB`
- GitHub: <https://github.com/1Panel-dev/MaxKB>
- Docs: <https://docs.maxkb.pro/>
- Why it stands out:
  - designed for enterprise-grade agents and RAG
  - supports local and hosted models
  - supports knowledge bases built from offline docs, tables, QA pairs, and websites
  - exposes an OpenAI-compatible application API
- Research notes:
  - official docs say MaxKB supports offline documents, tables, QA pairs, and website knowledge bases
  - official docs also describe OpenAI-compatible chat endpoints and support for Ollama/OpenAI-style model providers
- Fit for this project:
  - very good if we want a maintainable UI, knowledge import, and app API quickly

2. `FastGPT`
- GitHub: <https://github.com/labring/FastGPT>
- Docs: <https://doc.fastgpt.io/en/docs/introduction>
- Why it stands out:
  - knowledge-base-first architecture
  - strong visual workflow orchestration
  - multiple import modes including manual QA pairs and CSV import
  - designed for question-answering systems
- Research notes:
  - official docs describe it as a knowledge base Q&A system with RAG retrieval and visual workflow orchestration
  - knowledge-base docs include manual QA input, QA split, direct chunking, and CSV import
- Fit for this project:
  - strongest choice if we want explicit QA-pair management plus workflow control

3. `Open WebUI`
- GitHub: <https://github.com/open-webui/open-webui>
- Docs: <https://docs.openwebui.com/features/workspace/knowledge/>
- Why it stands out:
  - simple local deployment path
  - pairs well with Ollama
  - knowledge-base support includes hybrid retrieval and API management
- Research notes:
  - official docs show knowledge bases with file upload, retrieval modes, and REST API support
- Fit for this project:
  - best lightweight prototype path, weaker as a structured question-bank backend than MaxKB/FastGPT

### Tier B: strong but heavier or more specialized

4. `Dify`
- GitHub: <https://github.com/langgenius/dify>
- Docs: <https://docs.dify.ai/en/guides/knowledge-base/readme>
- Fit:
  - good if we later want more workflow and app orchestration than direct QA-pair operations

5. `RAGFlow`
- GitHub: <https://github.com/infiniflow/ragflow>
- Fit:
  - strong for complex document parsing and advanced RAG, but heavier than needed for a first build

6. `QAnything`
- GitHub: <https://github.com/netease-youdao/QAnything>
- Fit:
  - strong local knowledge-base project, especially if document QA matters more than explicit question-bank structure

7. `Langchain-Chatchat`
- GitHub: <https://github.com/chatchat-space/Langchain-Chatchat>
- Fit:
  - flexible local RAG stack with broad model compatibility, but more engineering-led than product-led

## 4. Local Model Serving Options

### Recommended serving layer

1. `Ollama`
- Docs: <https://docs.ollama.com/api/openai-compatibility>
- Why:
  - easiest local model runtime for a first prototype
  - official OpenAI-compatibility support

2. `LM Studio`
- Docs: <https://lmstudio.ai/docs/developer/core/server>
- Why:
  - easy GUI-based local serving
  - official docs expose OpenAI-compatible endpoints

3. `vLLM`
- Docs: <https://docs.vllm.ai/en/latest/serving/openai_compatible_server/>
- Why:
  - better high-performance serving path later
  - more suitable once the service shape is stable

## 5. Public Question-Bank and Benchmark Sources

These are useful as seed data, evaluation sets, or schema references. They are not all production-ready answer banks, and licenses must be checked before ingestion.

1. `C-Eval`
- Repo: <https://github.com/hkust-nlp/ceval>
- Notes:
  - official repo describes `13,948` multiple-choice questions across `52` disciplines
  - dataset can be loaded from Hugging Face
  - useful as structured MCQ seed data and evaluation material

2. `CMMLU`
- Repo: <https://github.com/haonan-li/CMMLU>
- Notes:
  - official repo describes a Chinese benchmark covering `67` topics
  - useful for Chinese knowledge-domain coverage and evaluation

3. `M3KE`
- Repo: <https://github.com/tjunlp-lab/M3KE>
- Notes:
  - official repo states `20,477` questions from `71` tasks
  - covers primary school to college and multiple disciplines
  - useful as large structured MCQ material

4. `CMMMU`
- Repo: <https://github.com/CMMMU-Benchmark/CMMMU>
- Notes:
  - multimodal benchmark with Chinese question material
  - useful only if image-based question support becomes a requirement

5. `AGIEval`
- Repo: <https://github.com/ruixiangcui/AGIEval>
- Notes:
  - useful as evaluation data and benchmarking reference
  - broader benchmark, less directly tailored to local Chinese study content than the three above

## 6. Current Implementation Decision

The project currently uses a custom Python local service instead of adopting MaxKB, FastGPT, or Open WebUI as the primary runtime.

Why:

- the final required output is an OCS-style source config calling a fixed local port
- a small custom service gives tighter control over response shape, handler compatibility, and source metadata
- OpenAI-compatible provider abstraction keeps both cloud APIs and local model runtimes available
- public benchmark data can be normalized directly into a project-owned JSONL index

MaxKB, FastGPT, and Open WebUI remain useful later if an admin UI, large-scale document ingestion, or visual workflow layer becomes more important.

## 7. Platform Options If A Product UI Is Needed

If a product-led layer is needed later, evaluate:

1. `MaxKB + Ollama`
- best balance of local deployment, QA import, website/doc sync, and API compatibility

If we want slightly more workflow flexibility:

2. `FastGPT + Ollama`
- especially good if the source data will be turned into QA pairs or CSV imports

If we want a minimal prototype before committing:

3. `Open WebUI + Ollama`
- good for proving the retrieval and local model path before building a more structured backend

In all cases, Ollama can be replaced by any OpenAI-compatible cloud or self-hosted model endpoint.

## 8. External Question-Bank API Policy

Unknown free search APIs or scraped websites should not be default dependencies. Most public snippets found online do not provide enough evidence for:

- stable API contract
- redistribution or usage license
- source attribution
- token safety
- long-term availability

The architecture keeps an external-source adapter boundary for future sources with explicit permission and a documented API contract.

## 9. Suggested Architecture Direction

Phase 1:

- choose one platform
- define a normalized question schema
- import a small clean sample question bank
- validate retrieval quality with manual review

Phase 2:

- add explanation generation backed by retrieved evidence
- add source attribution and answer confidence signals
- support structured imports from CSV/XLSX/JSON

Phase 3:

- expose a stable local HTTP API
- add tests for schema mapping, retrieval, and answer formatting
- decide whether an external client adapter is still needed

## 10. Selection Criteria For The Final Stack

Use these criteria before locking the stack:

- can ingest QA pairs directly
- can preserve original source fields and tags
- supports local model serving cleanly
- supports citation or source tracing
- stable API surface
- simple backup/export path
- acceptable Windows deployment experience

## 11. Immediate Next Step

Recommended next action:

- verify the local service from the user's real OCS environment

Why:

- the local automated config-client verifier already passes
- the remaining uncertainty is the real userscript/client runtime and the user's chosen model endpoint

