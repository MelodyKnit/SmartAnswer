# Normalized Indexes

Updated: `2026-06-07`

## 1. Purpose

This document records normalized local indexes generated from downloaded public sources.

## 2. Current Indexes

### CMMLU

- Path: `data\normalized\cmmlu.jsonl`
- Records: `11917`
- Source: `CMMLU`
- License note: `CC BY-NC-SA 4.0`
- Recommended use: default local study service index

### AGIEval MCQ

- Path: `data\normalized\agieval-mcq.jsonl`
- Records: `6154`
- Source: `AGIEval`
- License note: mixed upstream licenses; use for local evaluation and schema hardening unless task-level license review is complete
- Recommended use: optional extension index

### Verified Combined

- Path: `data\normalized\verified.jsonl`
- Records: `18071`
- Sources:
  - `CMMLU`: `11917`
  - `AGIEval`: `6154`
- Recommended use: broader local lookup testing

## 3. Regeneration

Run:

```powershell
python scripts\verify_exports.py
```

This regenerates:

- `data\normalized\cmmlu.jsonl`
- `data\normalized\agieval-mcq.jsonl`
- `data\normalized\verified.jsonl`

It also writes:

```text
data\manifests\export-verification.json
```

## 4. Service Usage

Default:

```powershell
.\scripts\start_service.ps1
```

Use the broader verified index:

```powershell
.\scripts\start_service.ps1 -Index data\normalized\verified.jsonl
```

