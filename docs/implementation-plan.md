# Implementation Plan

Updated: `2026-06-07`

## 1. Locked Decisions

The first implementation path is locked:

1. platform: custom Python local service
2. model provider: OpenAI-compatible endpoint
3. first verified dataset: CMMLU
4. broader verified dataset: CMMLU plus AGIEval MCQ
5. canonical import format: JSONL records using `CanonicalQuestionRecord`

This decision was chosen because the final required user workflow is an OCS-style configuration calling a fixed local service endpoint.

## 2. Why OpenAI-Compatible Provider First Is Reasonable

Using an OpenAI-compatible API boundary gives:

- direct support for hosted APIs
- direct support for local runtimes such as Ollama, LM Studio, or vLLM
- no need to expose API keys in OCS config
- one provider contract for fallback and explanation generation

Use cloud APIs when:

- answer quality matters more than local-only execution
- local hardware is limited
- the user wants quick validation

Use local runtimes when:

- privacy needs increase
- usage volume makes hosted costs undesirable
- the model stack needs full offline control

## 3. Milestones

### Milestone 1: foundation

- create project skeleton
- choose stack
- document environment bootstrap
- define canonical schema

Status: complete.

### Milestone 2: ingestion

- import curated QA CSV
- add normalization rules
- record source metadata
- add duplicate detection

Status: partially complete. CMMLU and AGIEval MCQ imports are implemented; duplicate hardening can be expanded later.

### Milestone 3: retrieval

- exact and fuzzy retrieval
- hybrid retrieval if chosen platform supports it
- confidence scoring

Status: complete for exact and fuzzy retrieval; vector or hybrid retrieval remains future work.

### Milestone 4: explanation

- add model-backed explanation generation
- require source-aware output
- mark fallback and low-confidence cases

Status: complete for OpenAI-compatible model fallback and explanation orchestration.

### Milestone 5: validation

- sample-based retrieval evaluation
- response contract tests
- provider health checks

Status: complete for unit tests, service checks, config-client simulation, export verification, and mock model fallback.

## 4. Recommended Folder Layout

```text
StudyQuestionBankAssistant/
  AGENTS.md
  README.md
  docs/
  data/
    manifests/
  scripts/
  src/
  tests/
```

## 5. Validation Gates Before Production Use

- schema validation passes for imports
- every successful result includes provenance
- low-confidence responses are flagged
- provider health endpoint is stable
- a hand-reviewed evaluation sample meets the agreed threshold

## 6. Evaluation Sample Design

Use three test groups:

1. exact-match curated questions
2. paraphrased questions with same answer
3. distractor-heavy questions with similar wording

Metrics to track:

- top-1 answer accuracy
- source hit rate
- explanation usefulness
- false confidence rate

## 7. Risks To Watch Early

- importing large noisy datasets before schema is stable
- relying on model guesses when retrieval missed
- mixing source licenses without recordkeeping
- coupling client mapping too early to backend design
- adopting local inference before baseline quality is known

## 8. Current Development Checklist

The project is ready for real-environment validation after:

- starting the service on the target port
- choosing the real model endpoint if LLM fallback is needed
- loading the OCS config in the user's actual client
- confirming userscript connection permissions for `127.0.0.1` or `localhost`

