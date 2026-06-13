#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv venv --clear
uv pip install -e '.[dev]'

echo "Installed wattle-tbench-harness environment."
echo "Harbor: $(command -v harbor || true)"
