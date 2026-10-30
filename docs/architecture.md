# Architecture

This template targets small self-hosted services:

- FastAPI APIs
- Node frontends
- worker/background containers
- simple compose-only services

## Layout

- `app/`: minimal example service entrypoint.
- `compose/`: local and Portainer-focused compose files.
- `scripts/`: CI/local utility scripts for checks, tests, builds.
- `.github/workflows/ci.yml`: validation, testing, audit, and image build/push flow.

## CI Design

1. Validate: Hadolint, Gitleaks, Compose config, tests, dependency audit.
2. Build: always builds image.
3. Push: only on `main` pushes.
