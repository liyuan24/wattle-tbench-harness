#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export npm_config_cache="${npm_config_cache:-/tmp/npm-cache}"

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

retry apt-get update
retry apt-get install -y --no-install-recommends \
  ca-certificates curl git nodejs npm
apt-get clean
rm -rf /var/lib/apt/lists/*

mkdir -p "$HOME/.codex"
cp /installed-agent/codex-auth.json "$HOME/.codex/auth.json"
if [[ -f /installed-agent/codex-config.toml ]]; then
  cp /installed-agent/codex-config.toml "$HOME/.codex/config.toml"
fi
chmod 700 "$HOME/.codex"
find "$HOME/.codex" -type f -exec chmod 600 {} +

retry npm install -g --no-audit --no-fund @openai/codex@latest
codex --version >/dev/null
rm -rf "$npm_config_cache"
