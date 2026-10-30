#!/usr/bin/env bash
set -euo pipefail
python -m ruff check app tests scripts/bundle_stations.py
python -m ruff format --check app tests scripts/bundle_stations.py
hadolint --config .hadolint.yaml Dockerfile
gitleaks detect --source . --config .gitleaks.toml --no-git --redact
# Dummy non-secret values, not a committed or generated .env file.
RAIL_IMAGE=jonesdavidj/rail:test RAIL_PLATFORM=linux/amd64 RAIL_HOST_PORT=8097 \
RAIL_VOLUME_NAME=rail-data RAIL_DATA_PATH=/data RAIL_PROVIDER=demo TZ=Europe/London \
  docker compose -f compose.yaml config --quiet
