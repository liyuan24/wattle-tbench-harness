#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-terminal-bench-for-wattle}"
ZONE="${ZONE:-us-central1-a}"
INSTANCE="${INSTANCE:-tbench-amd64}"
WATTLE_AUTH_PATH="${WATTLE_AUTH_PATH:-$HOME/.wattle/auth.json}"
CODEX_AUTH_PATH="${CODEX_AUTH_PATH:-$HOME/.codex/auth.json}"
CODEX_CONFIG_PATH="${CODEX_CONFIG_PATH:-$HOME/.codex/config.toml}"

usage() {
  cat <<EOF
Usage: $0 [options]

Copy local Wattle/Codex auth files to a GCP VM.

Options:
  --project PROJECT             Default: $PROJECT
  --zone ZONE                   Default: $ZONE
  --instance INSTANCE           Default: $INSTANCE
  --wattle-auth PATH            Default: $WATTLE_AUTH_PATH
  --codex-auth PATH             Default: $CODEX_AUTH_PATH
  --codex-config PATH           Default: $CODEX_CONFIG_PATH
  -h, --help

Environment variables with the same uppercase names are also supported.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project)
      PROJECT="$2"
      shift 2
      ;;
    --zone)
      ZONE="$2"
      shift 2
      ;;
    --instance)
      INSTANCE="$2"
      shift 2
      ;;
    --wattle-auth)
      WATTLE_AUTH_PATH="$2"
      shift 2
      ;;
    --codex-auth)
      CODEX_AUTH_PATH="$2"
      shift 2
      ;;
    --codex-config)
      CODEX_CONFIG_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '[error] unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_file() {
  local path="$1"
  local name="$2"
  if [ ! -f "$path" ]; then
    printf '[error] %s not found: %s\n' "$name" "$path" >&2
    exit 2
  fi
}

run_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    gcloud "$@"
  elif [ -x "$HOME/.local/google-cloud-sdk-install/google-cloud-sdk/bin/gcloud" ]; then
    "$HOME/.local/google-cloud-sdk-install/google-cloud-sdk/bin/gcloud" "$@"
  else
    printf '[error] gcloud not found on PATH or local SDK install path.\n' >&2
    exit 2
  fi
}

require_file "$WATTLE_AUTH_PATH" "Wattle auth"
require_file "$CODEX_AUTH_PATH" "Codex auth"
require_file "$CODEX_CONFIG_PATH" "Codex config"

printf '[auth] Preparing remote auth directories on %s\n' "$INSTANCE"
run_gcloud compute ssh "$INSTANCE" \
  "--project=$PROJECT" \
  "--zone=$ZONE" \
  --command 'mkdir -p ~/.wattle ~/.codex && chmod 700 ~/.wattle ~/.codex'

printf '[auth] Copying Wattle auth\n'
run_gcloud compute scp "$WATTLE_AUTH_PATH" "$INSTANCE:~/.wattle/auth.json" \
  "--project=$PROJECT" \
  "--zone=$ZONE"

printf '[auth] Copying Codex auth\n'
run_gcloud compute scp "$CODEX_AUTH_PATH" "$INSTANCE:~/.codex/auth.json" \
  "--project=$PROJECT" \
  "--zone=$ZONE"

printf '[auth] Copying Codex config\n'
run_gcloud compute scp "$CODEX_CONFIG_PATH" "$INSTANCE:~/.codex/config.toml" \
  "--project=$PROJECT" \
  "--zone=$ZONE"

printf '[auth] Fixing remote permissions\n'
run_gcloud compute ssh "$INSTANCE" \
  "--project=$PROJECT" \
  "--zone=$ZONE" \
  --command 'chmod 600 ~/.wattle/auth.json ~/.codex/auth.json ~/.codex/config.toml && ls -l ~/.wattle/auth.json ~/.codex/auth.json ~/.codex/config.toml'

printf '\n[auth] Auth files copied to %s.\n' "$INSTANCE"
