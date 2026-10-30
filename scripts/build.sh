#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-ghcr.io/your-org/your-service:local}"

docker build -t "${IMAGE_NAME}" .

echo "Built ${IMAGE_NAME}"
