#!/usr/bin/env bash
set -euo pipefail

WATTLE_REPO="${WATTLE_REPO:-https://github.com/liyuan24/wattle.git}"
HARNESS_REPO="${HARNESS_REPO:-https://github.com/liyuan24/wattle-tbench-harness.git}"
HARNESS_BRANCH="${HARNESS_BRANCH:-codex/container-backed-tui-tasks}"
CODEX_CLI_VERSION="${CODEX_CLI_VERSION:-0.140.0}"
REPOS_DIR="${REPOS_DIR:-$HOME/repos}"
WATTLE_DIR="$REPOS_DIR/wattle"
HARNESS_DIR="$REPOS_DIR/wattle-tbench-harness"

log() {
  printf '\n[bootstrap] %s\n' "$*"
}

require_ubuntu() {
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [ "${ID:-}" != "ubuntu" ]; then
      log "warning: expected Ubuntu, found ${PRETTY_NAME:-unknown OS}"
    fi
  fi
}

install_system_packages() {
  log "Installing system packages"
  sudo apt-get update
  sudo apt-get install -y \
    ca-certificates \
    curl \
    git \
    jq \
    python3 \
    python3-venv \
    tmux
}

install_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker"
    curl -fsSL https://get.docker.com | sudo sh
  else
    log "Docker already installed"
  fi

  if ! groups "$USER" | tr ' ' '\n' | grep -qx docker; then
    log "Adding $USER to docker group"
    sudo usermod -aG docker "$USER"
    DOCKER_GROUP_CHANGED=1
  else
    DOCKER_GROUP_CHANGED=0
  fi

  sudo systemctl enable --now docker
}

install_node_and_codex() {
  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
  if [ "$node_major" -lt 20 ]; then
    log "Installing Node.js 22"
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
  else
    log "Node.js already installed: $(node --version)"
  fi

  if command -v codex >/dev/null 2>&1; then
    log "Codex CLI already installed: $(codex --version)"
  else
    log "Installing Codex CLI @openai/codex@$CODEX_CLI_VERSION"
    sudo npm install -g "@openai/codex@$CODEX_CLI_VERSION"
    log "Codex CLI installed: $(codex --version)"
  fi
}

clone_or_update_repo() {
  local repo_url="$1"
  local repo_dir="$2"
  local branch="${3:-}"

  mkdir -p "$REPOS_DIR"
  if [ -d "$repo_dir/.git" ]; then
    log "Updating $repo_dir"
    git -C "$repo_dir" fetch --all --prune
  else
    log "Cloning $repo_url"
    git clone "$repo_url" "$repo_dir"
  fi

  if [ -n "$branch" ]; then
    git -C "$repo_dir" checkout "$branch"
    git -C "$repo_dir" pull --ff-only origin "$branch"
  else
    git -C "$repo_dir" pull --ff-only || true
  fi
}

setup_harness() {
  log "Installing harness dependencies"
  cd "$HARNESS_DIR"
  ./setup.sh

  log "Applying Harbor patches"
  .venv/bin/python scripts/patch_harbor_upload_dir.py
  .venv/bin/python scripts/patch_harbor_agent_timeout.py
  .venv/bin/python scripts/check_harbor_patch.py

  log "Running focused harness tests"
  .venv/bin/python -m pytest tests/test_harbor_runner.py tests/test_tui_task_runner.py -q
}

print_next_steps() {
  cat <<EOF

[bootstrap] VM setup complete.

If this script added you to the docker group, disconnect and SSH back in before
starting the benchmark:

  exit
  gcloud compute ssh tbench-amd64 --project=terminal-bench-for-wattle --zone=us-central1-a

Copy auth files from Spark/local machine to the VM:

  gcloud compute ssh tbench-amd64 --project=terminal-bench-for-wattle --zone=us-central1-a --command 'mkdir -p ~/.wattle ~/.codex && chmod 700 ~/.wattle ~/.codex'
  gcloud compute scp ~/.wattle/auth.json tbench-amd64:~/.wattle/auth.json --project=terminal-bench-for-wattle --zone=us-central1-a
  gcloud compute scp ~/.codex/auth.json tbench-amd64:~/.codex/auth.json --project=terminal-bench-for-wattle --zone=us-central1-a
  gcloud compute scp ~/.codex/config.toml tbench-amd64:~/.codex/config.toml --project=terminal-bench-for-wattle --zone=us-central1-a
  gcloud compute ssh tbench-amd64 --project=terminal-bench-for-wattle --zone=us-central1-a --command 'chmod 600 ~/.wattle/auth.json ~/.codex/auth.json ~/.codex/config.toml'

Start the official amd64 run on the VM:

  cd "$HARNESS_DIR"
  ./run_tbench.py \\
    --model codex/gpt-5.5 \\
    --effort high \\
    --n-attempts 1 \\
    --n-concurrent 2 \\
    --source-dir "$WATTLE_DIR" \\
    --tmux

Resume the latest interrupted run:

  cd "$HARNESS_DIR"
  ./run_tbench.py \\
    --model codex/gpt-5.5 \\
    --effort high \\
    --n-attempts 1 \\
    --n-concurrent 2 \\
    --source-dir "$WATTLE_DIR" \\
    --resume \\
    --tmux

Sync latest run back to Spark/local machine:

  ./scripts/sync_gcp_run.py --project terminal-bench-for-wattle --zone us-central1-a --instance tbench-amd64
EOF
}

main() {
  require_ubuntu
  install_system_packages
  install_docker
  install_node_and_codex
  clone_or_update_repo "$WATTLE_REPO" "$WATTLE_DIR"
  clone_or_update_repo "$HARNESS_REPO" "$HARNESS_DIR" "$HARNESS_BRANCH"
  setup_harness
  print_next_steps
}

main "$@"
