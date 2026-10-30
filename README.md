# home-server-service-template

Template repository for self-hosted Docker/Portainer/GitHub workflows.

## Included

- VS Code dev container
- GitHub Actions CI
- Gitleaks secret scan
- Hadolint Dockerfile lint
- Compose validation
- Test execution helper
- Dependency audit hooks
- Docker image build + optional push on main
- Portainer stack compose file

## Quick start for a new service

1. Click **Use this template** to create a new repo.
2. Rename image placeholders:
   - `ghcr.io/your-org/your-service`
3. Replace `app/` with your service code.
4. Update compose env defaults and ports.
5. Add real tests (`tests/test_*.py` or `npm test`).
6. Configure repo settings:
   - enable Actions
   - add any required secrets

## First required edits after duplication

- Change image names in compose files and CI.
- Update service name and docs.
- Replace placeholder env var defaults.
- Decide whether to keep Python base image or switch for Node/worker runtime.

## Commands

- `make check` — lint + secret scan + compose validate
- `make test` — run tests (or report none present)
- `make build` — build Docker image
- `make ci` — run all local CI-like tasks

See `docs/architecture.md`, `docs/deployment.md`, and `docs/operations.md`.

## Deploy (demo)

The current app is a minimal demo HTTP service, with no live rail-data integration.
Use the root `compose.yaml` for Portainer on Docker Standalone. No NAS mount,
external network, or committed `.env` is needed. The image runs as UID/GID 10001,
with tzdata installed, on port 8097. Only `/data` (local named volume) and `/tmp`
(tmpfs) are writable application paths; capabilities are dropped and privilege
escalation is disabled.

First deployment, in order:

1. Create a Docker Hub repository named `rail` in your account (public for
   unauthenticated Portainer pulls). Create a Docker Hub access token with write
   permission for that repository.
2. In this GitHub repo, Settings → Secrets and variables → Actions, add repository
   secrets `DOCKERHUB_USERNAME` (your Docker Hub account) and `DOCKERHUB_TOKEN`
   (the write token). These match `jonesdavidj/power-map`. Enable GitHub Actions.
3. Push/merge this change to `main`. Wait for CI to pass and publish both
   `docker.io/<username>/rail:main` and `:sha-<7-character-commit>`.
4. In Portainer, choose your Docker Standalone environment → Stacks → Add stack.
   Name it `rail`, choose Repository, enter `https://github.com/jonesdavidj/rail`,
   reference `refs/heads/main`, and Compose path `compose.yaml`. If the GitHub repo
   is private, configure repository authentication with read access. If the Docker
   Hub image is private, first add authenticated Docker Hub registry access in
   Portainer and select it for this stack.
5. In stack environment variables, set `DOCKERHUB_USERNAME` to the account from
   step 1. Leave `RAIL_DATA_API_KEY` empty. All other variables are optional:

   | Variable | Default |
   | --- | --- |
   | `DOCKERHUB_USERNAME` | `jonesdavidj` (override if different) |
   | `RAIL_IMAGE_TAG` | `main` |
   | `RAIL_CONTAINER_NAME` | `rail` |
   | `RAIL_RESTART_POLICY` | `unless-stopped` |
   | `TZ` | `Europe/London` |
   | `RAIL_HOST_PORT` | `8097` |
   | `RAIL_DATA_VOLUME` | `rail-data` |
   | `RAIL_TMP_SIZE` | `16m` |
   | `RAIL_READ_ONLY` | `true` |
   | `RAIL_DATA_API_KEY` | empty; no key needed for demo |

   `.env.example` documents the same variables; do not commit a `.env`.
   Keep the security defaults. Port 8097 must be available on the Docker host.
6. Deploy the stack. Docker creates the local `rail-data` volume automatically;
   a new volume inherits `/data` ownership from the image. Verify container `rail`
   becomes healthy and `http://<docker-host>:8097/api/health` returns
   `{"status":"ok","service":"rail","mode":"demo"}` (JSON spacing may differ).
   Open `http://<docker-host>:8097/` for the demo response. On later updates,
   pull/redeploy the stack to refresh `main`, or set `RAIL_IMAGE_TAG` to a published
   `sha-…` tag for an exact version. Do not delete the volume during updates.

CI runs only Ruff and pytest on pull requests (plus checkout/tool setup). Pushes
to `main` run the same checks, then one cached Docker build/push. The target is
under 60 seconds on a warm cache; registry and runner latency can exceed this.
Every job has a five-minute timeout and superseded runs are cancelled.

Local verification (2026-10-30): `docker compose config` passed; the composed
container became healthy without an API key, ran as UID 10001 with a read-only
root filesystem, and could write to `/data` and `/tmp`. Image size:
123,655,795 bytes (123.7 MB / 117.9 MiB, uncompressed). Local equivalents of CI
steps: tool installation 4.665 s, Ruff 0.007 s, pytest 1.263 s (2 passed), initial
Docker build 6.870 s, final build with base/layers cached 2.853 s. Actual GitHub
checkout/setup/login/cache-export/push timings have not been measured; a GitHub
Actions run is required to verify the under-60-second target.
