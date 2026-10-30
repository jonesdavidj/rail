#!/usr/bin/env bash
set -euo pipefail
python -m ruff check app tests scripts/bundle_stations.py
python -m ruff format --check app tests scripts/bundle_stations.py
hadolint --config .hadolint.yaml Dockerfile
gitleaks detect --source . --config .gitleaks.toml --no-git --redact
# Dummy non-secret values, not a committed or generated .env file.
RAIL_IMAGE=jonesdavidj/rail:test RAIL_PLATFORM=linux/amd64 RAIL_HOST_PORT=8097 \
RAIL_VOLUME_NAME=rail-data RAIL_DATA_PATH=/data RAIL_PROVIDER=demo TZ=Europe/London \
RAIL_DATA_BASE_URL= RAIL_DATA_ALLOWED_HOSTS=api1.raildata.org.uk RAIL_DATA_API_KEY= \
RAIL_DATA_API_KEY_FILE= ADMIN_TOKEN= RAIL_CACHE_TTL=30 RAIL_REFRESH_SECONDS=30 \
  docker compose -f compose.yaml config --quiet
