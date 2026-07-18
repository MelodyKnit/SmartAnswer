# StudyQuestionBankAssistant

This workspace is for a local question-bank and LLM study assistant. The current implementation provides a local HTTP service, normalized public benchmark question indexes, an OpenAI-compatible model provider, and an OCS-style source configuration.

## Goal

Build a stable, self-hostable foundation for:

- question-bank ingestion
- retrieval over structured or semi-structured question data
- local or hosted OpenAI-compatible LLM answer generation with explanation and citation
- manual review before any downstream use

## Boundary

This workspace is organized for compliant study and review scenarios. The intended output is a retrievable knowledge service and local assistant, not an auto-submit or exam-bypass workflow.

## Current Status

- dedicated project workspace and rules are established
- public source research and source verification are documented
- CMMLU and AGIEval MCQ were normalized into local JSONL indexes
- local `/query` and OCS-style `/ocs/query` endpoints are implemented
- OCS-style config is available as a static file and from the running service
- OpenAI-compatible model fallback and explanation mode are implemented
- unit, export, service, config-client, and mock-model acceptance checks pass

## Preferred Architecture Direction

The implemented path is a custom Python local service with pluggable sources and an OpenAI-compatible model provider. This avoids coupling the OCS config to any single model runtime.

Recommended model options:

1. Cloud OpenAI-compatible API
   Best for answer quality and low local hardware requirements.
2. Local OpenAI-compatible runtime such as Ollama, LM Studio, or vLLM
   Best when privacy, offline use, or local control matters more.
3. MaxKB or FastGPT integration later
   Useful if a web admin UI and large-scale QA import workflow become more important than a lightweight service.

## Documentation Map

- Research notes: [docs/research.md](docs/research.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- API contract: [docs/api-contract.md](docs/api-contract.md)
- Data sources: [docs/data-sources.md](docs/data-sources.md)
- Normalized indexes: [docs/normalized-indexes.md](docs/normalized-indexes.md)
- Source verification: [docs/source-verification.md](docs/source-verification.md)
- Ingestion mapping: [docs/ingestion-mapping.md](docs/ingestion-mapping.md)
- Stack decision: [docs/stack-decision.md](docs/stack-decision.md)
- Environment setup: [docs/environment.md](docs/environment.md)
- Local service: [docs/local-service.md](docs/local-service.md)
- Model provider: [docs/model-provider.md](docs/model-provider.md)
- External client adapter: [docs/external-client-adapter.md](docs/external-client-adapter.md)
- OCS-style adapter: [docs/ocs-adapter.md](docs/ocs-adapter.md)
- OCS usage runbook: [docs/ocs-usage-cn.md](docs/ocs-usage-cn.md)
- Acceptance workflow: [docs/acceptance.md](docs/acceptance.md)
- Delivery status: [docs/delivery-status.md](docs/delivery-status.md)
- Implementation plan: [docs/implementation-plan.md](docs/implementation-plan.md)

## Current Working Commands

Create and activate the project environment:

```powershell
conda env create -f environment.yml
conda activate ai-study-qb
```

Copy local environment variables and fill your own secrets:

```powershell
Copy-Item .env.example .env
```

Start the FastAPI service:

```powershell
.\scripts\run.ps1
```

Development mode with reload:

```powershell
.\scripts\run.ps1 --dev
```

Bash equivalents are also available:

```bash
./scripts/run.sh
./scripts/run.sh --dev
```

Enable an OpenAI-compatible model provider in `.env`:

```dotenv
STQB_LLM_BASE_URL=https://api.example.com/v1
STQB_LLM_MODEL=your-model-name
STQB_LLM_API_KEY=your-api-key
```

Run backend validation:

```powershell
pytest -q
ruff check src tests
mypy src\study_qb_assistant
```

Run frontend validation:

```powershell
cd src\website
npm install
npm run build
```

Docker deployment uses the immutable image reference recorded in `.env.release`:

```bash
cp .env.release.example .env.release
docker compose --env-file .env.release up -d --no-build
```

Before any server sync or deployment, bump the version in `pyproject.toml` first
and create the matching Git tag, for example `v0.1.6`.
Treat code upload, image publication, and `docker compose up -d --no-build` on the server as a release step,
not as ordinary local debugging.

Recommended release order:

1. Finish the code change and self-check it locally.
2. Update `pyproject.toml` `version`.
3. Run the minimal required validation.
4. Commit the release change and create the matching `vX.Y.Z` tag.
5. Then sync to the server or rebuild the deployment.

The Docker image builds the frontend and backend together. Runtime data is written to
`deploy-data/` on the server and starts empty by default; local `data/` files are not
required and are not copied into the image.
Tagged releases publish a private GHCR image and `release-manifest.json`. When the GitHub
deployment variables and secrets are configured, the same tag workflow updates the existing
Docker deployment over SSH. No updater service, Docker socket, or GitHub credential is added
to the application container; see [docs/deployment.md](docs/deployment.md) for the one-time
GitHub repository setup.
For production vision-question support, set `STQB_PUBLIC_BASE_URL` to the public HTTPS
origin of the service. OCS question images are stored under `deploy-data/images/ocs/`
and exposed as `/api/v1/media/ocs/images/<sha256>.<ext>` for vision models.

Install and run commit hooks:

```powershell
pre-commit install
pre-commit run --all-files
```

Python hooks explicitly run in the project Conda environment `ai-study-qb`, so these commands
behave consistently even when they are invoked from another active Conda environment.

Quick API smoke checks:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/healthz"
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/status"
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/configs/ocs-local-study-bank.json"
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ocs/query?title=示例题&type=single"
```
