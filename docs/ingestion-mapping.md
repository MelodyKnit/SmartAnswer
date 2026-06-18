# Ingestion Mapping

Updated: `2026-06-07`

## 1. Purpose

This document maps verified upstream source formats into the canonical question schema described in [api-contract.md](../docs/api-contract.md) and [architecture.md](../docs/architecture.md).

## 2. Canonical Internal Fields

Target internal fields:

- `question_id`
- `title_raw`
- `question_type`
- `options_raw`
- `answer_raw`
- `explanation`
- `subject`
- `chapter`
- `tags`
- `source_name`
- `source_url`
- `source_license`
- `source_split`

## 3. CMMLU Mapping

Sample source:

- [anatomy.csv](../data/raw/cmmlu-upstream/data/dev/anatomy.csv)

Observed source columns:

- unnamed row index
- `Question`
- `A`
- `B`
- `C`
- `D`
- `Answer`

Mapping:

- `question_id` <- file stem + row index
- `title_raw` <- `Question`
- `question_type` <- `single`
- `options_raw` <- `[A, B, C, D]`
- `answer_raw` <- `Answer`
- `explanation` <- empty
- `subject` <- file stem such as `anatomy`
- `chapter` <- empty
- `tags` <- `["cmmlu"]`
- `source_name` <- `CMMLU`
- `source_url` <- upstream repo URL
- `source_license` <- `CC BY-NC-SA 4.0`
- `source_split` <- parent directory such as `dev` or `test`

Import difficulty:

- low

## 4. M3KE Mapping

Sample source:

- [Advanced Mathematics-Natural Sciences-College.jsonl](../data/raw/m3ke-upstream/data/dev/Advanced%20Mathematics-Natural%20Sciences-College.jsonl)

Observed source fields:

- `id`
- `question`
- `A`
- `B`
- `C`
- `D`
- `answer`

Mapping:

- `question_id` <- file stem + `id`
- `title_raw` <- `question`
- `question_type` <- `single`
- `options_raw` <- `[A, B, C, D]`
- `answer_raw` <- `answer`
- `explanation` <- empty
- `subject` <- parse from file stem before the first delimiter group
- `chapter` <- empty
- `tags` <- parsed discipline and level plus `m3ke`
- `source_name` <- `M3KE`
- `source_url` <- upstream repo URL
- `source_license` <- `unknown-needs-confirmation`
- `source_split` <- parent directory such as `dev` or `test`

Import difficulty:

- low technically
- medium operationally because license confirmation is still needed

## 5. AGIEval Mapping

Sample source:

- [gaokao-physics.jsonl](../data/raw/agieval-upstream/data/v1_1/gaokao-physics.jsonl)

Observed source fields:

- `passage`
- `question`
- `options`
- `label`
- `answer`
- `other`

Mapping:

- `question_id` <- file stem + row number
- `title_raw` <- `question`
- `question_type` <- `single` for MCQ tasks
- `options_raw` <- `options`
- `answer_raw` <- `label` when present, else `answer`
- `explanation` <- empty
- `subject` <- file stem such as `gaokao-physics`
- `chapter` <- empty
- `tags` <- `["agieval", "v1_1"]`
- `source_name` <- `AGIEval`
- `source_url` <- upstream repo URL
- `source_license` <- `mixed-follow-original`
- `source_split` <- version directory such as `v1_1`

Special handling:

- if `passage` exists, preserve it in auxiliary metadata for future retrieval context
- preserve `other.source` when present

Import difficulty:

- medium, because some tasks are non-MCQ and license expectations differ by original dataset

## 6. C-Eval Planned Mapping

Current evidence:

- local repo contains documentation and mappings
- full dataset payload is referenced through Hugging Face

Expected fields from official README example:

- `id`
- `question`
- `A`
- `B`
- `C`
- `D`
- `answer`
- `explanation`

Planned mapping:

- `question_id` <- subject handler + `id`
- `title_raw` <- `question`
- `question_type` <- `single`
- `options_raw` <- `[A, B, C, D]`
- `answer_raw` <- `answer`
- `explanation` <- `explanation`
- `subject` <- subject handler
- `tags` <- subject category plus `ceval`
- `source_name` <- `C-Eval`
- `source_license` <- `CC BY-NC-SA 4.0`

## 7. Recommended First Import Order

1. CMMLU
2. M3KE
3. AGIEval MCQ subset
4. C-Eval after payload retrieval succeeds

## 8. Immediate Coding Implication

The first ingestion pipeline should support:

- CSV row readers
- JSONL row readers
- file-stem metadata parsing
- per-source license tagging
- split-aware provenance recording

