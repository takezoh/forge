#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FORGE_ROOT="$(dirname "$SCRIPT_DIR")"

exec "$FORGE_ROOT/.venv/bin/python3" -m agent "$@"
