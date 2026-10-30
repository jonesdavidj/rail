# Operations

## Local development

- Start dev container in VS Code.
- Run `make check`, `make test`, `make build`.
- Run compose locally: `docker compose -f compose/docker-compose.yml up --build`.

## CI gates

- secret scanning (Gitleaks)
- Dockerfile lint (Hadolint)
- compose validation (`docker compose config`)
- tests
- dependency audit
- image build

## Troubleshooting

- Validate compose manually:
  - `docker compose -f compose/docker-compose.yml config`
  - `docker compose -f compose/docker-compose.portainer.yml config`
- Re-run checks with `./scripts/check.sh`.
