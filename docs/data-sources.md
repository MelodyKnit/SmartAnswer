# Data Sources

Updated: `2026-06-07`

## 1. Source Categories

Potential data sources fall into four groups:

1. public benchmark datasets
2. self-curated QA tables
3. website knowledge imports
4. optional external live lookup services

For this project, public benchmark datasets and self-curated QA tables should be the first ingestion targets because they are the easiest to audit and normalize.

## 2. Public Benchmark Datasets

### 2.1 C-Eval

- Official repo: <https://github.com/hkust-nlp/ceval>
- Current value:
  - Chinese multiple-choice benchmark
  - official repo describes `13,948` questions across `52` disciplines
- Recommended use:
  - seed dataset
  - regression and retrieval evaluation set
- Caution:
  - confirm license and redistribution terms before bundling in-repo

### 2.2 CMMLU

- Official repo: <https://github.com/haonan-li/CMMLU>
- Current value:
  - broad Chinese subject coverage
  - official repo describes `67` topics
- Recommended use:
  - retrieval quality testing
  - subject taxonomy reference

### 2.3 M3KE

- Official repo: <https://github.com/tjunlp-lab/M3KE>
- Current value:
  - large Chinese education-oriented multiple-choice set
  - official repo states `20,477` questions from `71` tasks
- Recommended use:
  - seed import candidate
  - ingestion stress test

### 2.4 CMMMU

- Official repo: <https://github.com/CMMMU-Benchmark/CMMMU>
- Current value:
  - multimodal question material
- Recommended use:
  - only if image-based question support is added later

### 2.5 AGIEval

- Official repo: <https://github.com/ruixiangcui/AGIEval>
- Current value:
  - evaluation-oriented benchmark
- Recommended use:
  - benchmark and validation reference

## 3. Self-Curated QA Table Format

The most reliable first-party format for this project is:

- `CSV`
- `XLSX`
- `JSONL`

Suggested canonical columns:

- `question_id`
- `subject`
- `chapter`
- `question_type`
- `title`
- `options`
- `answer`
- `explanation`
- `tags`
- `source_name`
- `source_url`
- `source_license`

## 4. Website Knowledge Sources

Current strong candidates:

- `MaxKB` website knowledge base import
- `Open WebUI` knowledge management plus sync tooling

Appropriate use cases:

- static course notes
- documentation pages
- public educational references

Avoid using website import as the first and only answer source for objective questions when a structured QA table is available.

## 5. Optional External Live Lookup Sources

These should be treated as optional adapters, not primary dependencies.

Rules:

- source provenance must be recorded
- response shape must be normalized
- failures must not break the core service
- only use sources with clear authorization or clearly public access

Why they are lower priority:

- availability risk
- quality inconsistency
- legal and stability uncertainty
- difficult reproducibility

## 6. Intake Policy

Before importing any source, capture:

- source owner
- source URL
- access method
- license or usage note
- schema notes
- quality notes
- last verification date

## 7. Recommended Initial Data Strategy

Start with:

1. a small hand-verified QA table
2. one public benchmark dataset for scale testing
3. one documentation or website knowledge source for RAG behavior testing

This gives:

- one highly trusted source
- one large structured source
- one semi-structured source

## 8. Storage Recommendation For Raw Data

Do not commit large downloaded corpora into source directories immediately.

Prefer this future layout:

```text
StudyQuestionBankAssistant/
  data/
    raw/
    staged/
    normalized/
    manifests/
```

Store only lightweight manifests and documentation in versioned source control unless the chosen dataset license clearly allows bundling.

