#!/usr/bin/env bash
set -euo pipefail

hadolint --config .hadolint.yaml Dockerfile

gitleaks detect --source . --config .gitleaks.toml --no-git --redact

docker compose -f compose/docker-compose.yml config >/dev/null
docker compose -f compose/docker-compose.portainer.yml config >/dev/null

echo "Checks passed"
