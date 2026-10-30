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
