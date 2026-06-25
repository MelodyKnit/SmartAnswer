# Server Deployment

This project is deployed on Linux with Docker because the runtime requires Python 3.13 while the current server default Python may differ.

## Deployment assets

- `Dockerfile`: application image with Python 3.13, backend dependencies, and a built frontend
- `docker-compose.yaml`: one-command production service definition
- `.env.server`: server-local environment file, intentionally not committed
- `.env.server.example`: server-local environment template

The image only contains code, generated frontend static assets, and committed configs.
It does **not** carry local `data/` contents into production.

## Data boundary

Production paths are split into three categories:

- Image-only read-only assets:
  - `src/`
  - `scripts/`
  - `configs/`
- Runtime writable data on the server:
  - `deploy-data/runtime/`
  - `deploy-data/logs/`
  - `deploy-data/normalized/`
  - any later runtime cache files under `deploy-data/`
- Optional import assets:
  - manually uploaded or generated question-bank files after deployment

The default production deployment starts with an empty `deploy-data/normalized/`.
If `data/normalized/verified.jsonl` does not exist, the service still starts and exposes
health, auth, and admin pages. Query endpoints return a normal local not-found result until
question-bank data is imported later.

## Expected server-local environment

Minimum required values:

- none for first boot

Recommended deployment values:

- `STQB_LLM_BASE_URL`
- `STQB_LLM_MODEL`
- `STQB_LLM_API_KEY`
- `STQB_REQUIRE_AUTH=true`
- `STQB_REDIS_URL` only if shared session storage is needed

The compose file does not require `.env.server` to exist. You can boot the site first,
create the first `superadmin`, and then configure model/search providers from the admin UI.
If you prefer environment-based deployment, copy `.env.server.example` to `.env.server`
and fill server-local values; Compose loads it when present.

## First start

Start the service:

```bash
docker compose up -d --build
```

Docker creates `deploy-data/` automatically on first boot. The service uses
`STQB_DATA_DIR=/app/data` in the container, so database, logs, and optional normalized
question-bank files all live under the mounted server directory.

On a brand-new runtime database, the first registered user becomes `superadmin`.

## Importing question-bank data

Question-bank files are not bundled into production by default.
After the service is online, import or copy normalized data separately if needed, for example:

- place a normalized JSONL into `deploy-data/normalized/verified.jsonl`, or
- use later admin/import workflows when available

This keeps local work artifacts, caches, logs, and SQLite snapshots out of the deployment image.

## Reverse proxy

The service listens on container port `8765` and host port `3003`.
If Nginx is used, proxy `ocs.classbot.top` to `http://127.0.0.1:3003`.
