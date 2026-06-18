# Source Verification

Updated: `2026-06-07`

## 1. Purpose

This document records which public sources have been verified from authoritative evidence, what license conditions apply, whether data is locally available, and whether the source is suitable for direct ingestion into the project.

## 2. Verified Source Status

### 2.1 C-Eval

- Repo: <https://github.com/hkust-nlp/ceval>
- Local path: [data/raw/ceval-upstream](../data/raw/ceval-upstream)
- Authoritative evidence:
  - GitHub repo metadata reports code license as `MIT`
  - local repo includes `LICENSE-DATA`
  - local `README.md` says the dataset contains `13,948` multiple-choice questions across `52` disciplines
- Important license note:
  - the dataset license in local `LICENSE-DATA` is `CC BY-NC-SA 4.0`
- Current local status:
  - repo cloned successfully
  - dataset payload is not bundled directly in the repo
  - official README points to Hugging Face zip and datasets loading
- Import suitability:
  - suitable for internal, non-commercial research ingestion
  - not suitable for unrestricted redistribution
- Current limitation:
  - direct Hugging Face download was not reachable from the current environment during this session

### 2.2 CMMLU

- Repo: <https://github.com/haonan-li/CMMLU>
- Local path: [data/raw/cmmlu-upstream](../data/raw/cmmlu-upstream)
- Authoritative evidence:
  - local `README_EN.md` says CMMLU covers `67` topics
  - local repo contains a `data/` directory with CSV files
  - local `README_EN.md` has a license section pointing to `Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License`
  - sampled local file: [anatomy.csv](../data/raw/cmmlu-upstream/data/dev/anatomy.csv)
- Important license note:
  - local `README_EN.md` states the dataset is licensed under `CC BY-NC-SA 4.0`
- Current local status:
  - repo cloned successfully
  - `134` files found under local `data/`
  - format is directly usable for ingestion planning
- Import suitability:
  - strong candidate for first structured ingestion pass in non-commercial research mode

### 2.3 M3KE

- Repo: <https://github.com/tjunlp-lab/M3KE>
- Local path: [data/raw/m3ke-upstream](../data/raw/m3ke-upstream)
- Authoritative evidence:
  - local `README.md` says M3KE contains `20,477` questions from `71` tasks
  - local `README.md` says all questions are multiple-choice questions with four options
  - local repo contains a `data/` directory with JSONL files and `M3KE.zip`
  - sampled local file: [Advanced Mathematics-Natural Sciences-College.jsonl](../data/raw/m3ke-upstream/data/dev/Advanced%20Mathematics-Natural%20Sciences-College.jsonl)
- Important license note:
  - no explicit dataset license section was found in the local `README.md`
  - GitHub repo metadata did not expose a license
- Current local status:
  - repo cloned successfully
  - `143` files found under local `data/`
  - data format is directly ingestible
- Import suitability:
  - technically strong ingestion candidate
  - legal reuse status must be treated as `needs manual license confirmation`

### 2.4 AGIEval

- Repo: <https://github.com/ruixiangcui/AGIEval>
- Local path: [data/raw/agieval-upstream](../data/raw/agieval-upstream)
- Authoritative evidence:
  - GitHub repo metadata reports code license as `MIT`
  - local `README.md` says AGIEval v1.1 contains `20` tasks
  - local `README.md` says AGIEval v1.1 contains `18` MCQ tasks and two cloze tasks
  - local repo contains `data/` with JSONL task files and few-shot prompts
  - sampled local file: [gaokao-physics.jsonl](../data/raw/agieval-upstream/data/v1_1/gaokao-physics.jsonl)
- Important license note:
  - local `README.md` says use of the data should follow the license of the original datasets
  - treat as mixed-license and review-per-task before redistribution
- Current local status:
  - repo cloned successfully
  - `46` files found under local `data/`
  - `6154` MCQ records exported into `data\normalized\agieval-mcq.jsonl`
- Import suitability:
  - good for evaluation and schema testing
  - should not be treated as a single-license redistributable corpus

## 3. Platform Verification Snapshot

### 3.1 MaxKB

- Repo: <https://github.com/1Panel-dev/MaxKB>
- GitHub repo metadata:
  - license: `GPL-3.0`
  - default branch: `v2`
  - last checked update: `2026-06-06T23:17:57Z`
- Documentation evidence used earlier:
  - official docs describe dataset ingestion and API chat capabilities
- Current judgment:
  - strongest optional product-led layer if a maintainable web UI and knowledge-base admin workflow are needed later

### 3.2 FastGPT

- Repo: <https://github.com/labring/FastGPT>
- GitHub repo metadata:
  - license field reported as `NOASSERTION`
  - last checked update: `2026-06-07T02:06:34Z`
- Current judgment:
  - strong workflow and QA-ingestion candidate
  - license terms should be read directly from the repo before production adoption

### 3.3 Open WebUI

- Repo: <https://github.com/open-webui/open-webui>
- GitHub repo metadata:
  - license field reported as `NOASSERTION`
  - last checked update: `2026-06-07T04:49:15Z`
- Current judgment:
  - strong lightweight prototype path
  - verify repo license text directly before deeper adoption

### 3.4 Dify

- Repo: <https://github.com/langgenius/dify>
- GitHub repo metadata:
  - license field reported as `NOASSERTION`
  - last checked update: `2026-06-07T04:49:29Z`
- Current judgment:
  - strong orchestration platform
  - verify repo license text directly before deeper adoption

## 4. Recommended Source Priority

Use this order for implementation:

1. small hand-verified CSV
2. CMMLU for first structured bulk import
3. M3KE for larger-scale ingestion tests after license confirmation
4. AGIEval for evaluation and schema hardening
5. C-Eval full dataset after data payload download path is available

## 5. Current Reliability Note

The project now has locally available public benchmark data in `raw/` for three sources plus C-Eval repository materials. This is enough to begin ingestion pipeline development without waiting on additional web discovery.

