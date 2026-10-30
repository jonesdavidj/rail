#!/usr/bin/env bash
set -euo pipefail

if compgen -G "tests/test_*.py" > /dev/null; then
  python -m pytest -q
elif [ -f package.json ] && jq -e '.scripts.test' package.json >/dev/null 2>&1; then
  npm test
else
  echo "No tests found (expected tests/test_*.py or package.json test script)."
fi
