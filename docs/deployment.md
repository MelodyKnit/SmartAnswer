# Server Deployment

This project is deployed on Linux with Docker because the runtime requires Python 3.13 while the current server default Python may differ.

## Deployment assets

- `Dockerfile`: application image with Python 3.13, backend dependencies, and a built frontend
- `docker-compose.yaml`: one-command production service definition
- `.env.server`: server-local environment file, intentionally not committed
- `.env.server.example`: server-local environment template
- `.env.release`: current immutable image reference and release version
- `deploy/remote-release.sh`: a short-lived deployment script invoked by GitHub Actions

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
  - `deploy-data/images/ocs/`
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
- `STQB_PUBLIC_BASE_URL=https://your-public-domain`
- `STQB_REDIS_URL` only if shared session storage is needed

When the model gateway or outbound proxy runs on the host machine instead of inside the
same container network, use `host.docker.internal` rather than `127.0.0.1`.
Inside the container, loopback only points to the application container itself.
Vision questions store readable OCS images under `deploy-data/images/ocs/` and send the
model a URL under `/media/ocs/images/`. Configure `STQB_PUBLIC_BASE_URL` to the public
HTTPS origin that the model provider can reach; otherwise local loopback requests fall
back to inline data URLs for development.

The compose file does not require `.env.server` to exist. You can boot the site first,
create the first `superadmin`, and then configure model/search providers from the admin UI.
If you prefer environment-based deployment, copy `.env.server.example` to `.env.server`
and fill server-local values; Compose loads it when present.
The default server template points `STQB_LLM_BASE_URL` at `http://host.docker.internal:3000/v1`
so a host-side OpenAI-compatible gateway remains reachable from the container.
The server template also defaults `STQB_WEB_SEARCH_PROVIDER` to `bing`, which is the safer
choice when DuckDuckGo direct access is unstable in the deployment environment.

## First release start

Create `.env.release` from the template, then replace the image reference with the digest
published in the GitHub Release manifest:

```bash
cp .env.release.example .env.release
chmod 600 .env.release
docker login ghcr.io -u YOUR_GITHUB_USERNAME
docker pull ghcr.io/melodyknit/smartanswer@sha256:RELEASE_DIGEST
docker compose --env-file .env.release up -d --no-build
```

Docker creates `deploy-data/` automatically on first boot. The service uses
`STQB_DATA_DIR=/app/data` in the container, so database, logs, and optional normalized
question-bank files and OCS question images all live under the mounted server directory.
The image contains versioned prompts and default configs. On first use, the email-domain
whitelist is copied to `deploy-data/configs/email-domain-whitelist.json`; edit that runtime
copy when changing allowed registration domains. It is not overwritten by later images.

On a brand-new runtime database, the first registered user becomes `superadmin`.

## Private GitHub automatic updates

After the initial Docker deployment, no additional updater process needs to be installed on
the server. Creating a matching `vX.Y.Z` tag runs `.github/workflows/release.yml`: it tests,
builds and publishes the immutable GHCR image, creates the GitHub Release, then deploys that
exact image digest through one SSH session.

The first server setup still needs Docker, Docker Compose and an SSH account that can run
`docker compose`. The project directory must already contain `docker-compose.yaml`,
`.env.release` and the persistent `deploy-data/` directory. Configure the following values in
the GitHub repository, not in application configuration or server `.env` files:

| GitHub repository setting | Required value |
| --- | --- |
| Variable `DEPLOY_ENABLED` | `true` to enable automatic deployment; omit or set `false` to publish only |
| Variable `DEPLOY_HOST` | server host name or IP address |
| Variable `DEPLOY_PORT` | SSH port, default `22` |
| Variable `DEPLOY_USER` | server deployment user |
| Variable `DEPLOY_PATH` | absolute project directory on the server |
| Variable `DEPLOY_HEALTH_URL` | optional local health base URL, default `http://127.0.0.1:3003` |
| Secret `DEPLOY_SSH_PRIVATE_KEY` | private key whose public key is authorized for `DEPLOY_USER` |
| Secret `DEPLOY_KNOWN_HOSTS` | pinned `known_hosts` entry for the deployment host |
| Secret `GHCR_READ_TOKEN` | classic PAT with only `read:packages` for this private image |

The workflow passes the GHCR token over SSH standard input only. The remote script uses a
temporary Docker credential directory, pulls the immutable digest, creates a SQLite online
backup, replaces `.env.release` atomically and verifies `/healthz` plus `/version`. A failed
start or health check restores the prior image reference and database snapshot. The server
does not keep the GitHub or GHCR token, and the business container never receives Docker
access.

To obtain the pinned host key without trusting interactive SSH prompts, run this from a trusted
administrator machine and save the resulting line as `DEPLOY_KNOWN_HOSTS`:

```bash
ssh-keyscan -H your-server.example.com
```

Use a dedicated deployment SSH key when possible. The public half belongs in the server user's
`~/.ssh/authorized_keys`; the private half belongs only in the GitHub Actions secret.

## Importing question-bank data

Question-bank files are not bundled into production by default.
After the service is online, import or copy normalized data separately if needed, for example:

- place a normalized JSONL into `deploy-data/normalized/verified.jsonl`, or
- use later admin/import workflows when available

This keeps local work artifacts, caches, logs, and SQLite snapshots out of the deployment image.

## Reverse proxy

The service listens on container port `8765` and host port `3003`.
If Nginx is used, proxy `ocs.classbot.top` to `http://127.0.0.1:3003`.
