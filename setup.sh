#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
export UV_INSTALL_DIR="${UV_INSTALL_DIR:-/usr/local/bin}"
export UV_TOOL_BIN_DIR="${UV_TOOL_BIN_DIR:-/usr/local/bin}"
export UV_TOOL_DIR="${UV_TOOL_DIR:-/tmp/uv-tools}"
export PATH="$UV_TOOL_BIN_DIR:$UV_INSTALL_DIR:$HOME/.local/bin:$PATH"

retry() {
  local attempts="${RETRY_ATTEMPTS:-4}"
  local delay="${RETRY_DELAY_SECONDS:-3}"
  local attempt=1
  until "$@"; do
    local status=$?
    if (( attempt >= attempts )); then
      return "$status"
    fi
    echo "Command failed with status $status; retrying $attempt/$attempts: $*" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
  done
}

install_uv() {
  if command -v uv >/dev/null 2>&1 && [[ -x "$(command -v uv)" ]]; then
    return 0
  fi

  mkdir -p "$UV_INSTALL_DIR" "$UV_TOOL_BIN_DIR"
  if retry bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'; then
    command -v uv >/dev/null 2>&1 && [[ -x "$(command -v uv)" ]]
    return
  fi

  echo "uv install script failed; falling back to pip-installed uv" >&2
  retry apt-get update
  retry apt-get install -y --no-install-recommends python3-pip
  retry python3 -m pip install --break-system-packages --no-cache-dir uv
}

retry apt-get update
retry apt-get install -y --no-install-recommends \
  ca-certificates curl git python3 python3-venv tar gzip
apt-get clean
rm -rf /var/lib/apt/lists/*

mkdir -p "$UV_CACHE_DIR" "$UV_TOOL_DIR" "$UV_TOOL_BIN_DIR" "$UV_INSTALL_DIR"
install_uv

mkdir -p "$HOME/.wattle" "$HOME/.codex"
chmod 700 "$HOME/.wattle" "$HOME/.codex"

if [[ -f /installed-agent/wattle-auth.json ]]; then
  cp /installed-agent/wattle-auth.json "$HOME/.wattle/auth.json"
elif [[ -f /installed-agent/codex-auth.json ]]; then
  python3 - <<'PY'
import json
from pathlib import Path

source = Path("/installed-agent/codex-auth.json")
target = Path.home() / ".wattle" / "auth.json"
data = json.loads(source.read_text(encoding="utf-8"))

tokens = None
if isinstance(data, dict):
    if isinstance(data.get("tokens"), dict):
        tokens = data["tokens"]
    elif isinstance(data.get("access_token"), str):
        tokens = data
elif isinstance(data, list):
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("tokens"), dict):
            tokens = item["tokens"]
            break
        if isinstance(item, dict) and isinstance(item.get("access_token"), str):
            tokens = item
            break

if tokens is None:
    raise SystemExit("Could not derive Wattle OpenAI OAuth auth from codex-auth.json")

target.write_text(
    json.dumps({"openai": {"oauth": tokens}}, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
fi

if [[ -f /installed-agent/codex-auth.json ]]; then
  cp /installed-agent/codex-auth.json "$HOME/.codex/auth.json"
fi
if [[ -f /installed-agent/codex-config.toml ]]; then
  cp /installed-agent/codex-config.toml "$HOME/.codex/config.toml"
fi
find "$HOME/.wattle" "$HOME/.codex" -type f -exec chmod 600 {} +

rm -rf /tmp/wattle-src
mkdir -p /tmp/wattle-src
tar -xzf /installed-agent/wattle-source.tgz -C /tmp/wattle-src
retry uv --no-cache tool install --force -e /tmp/wattle-src
rm -rf "$UV_CACHE_DIR"

wattle --help >/dev/null
