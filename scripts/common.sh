#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# .env est lu comme données par Compose/Python, jamais exécuté par le shell.
dc() { docker compose "$@"; }
