#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-terminal-bench-for-wattle}"
ZONE="${ZONE:-us-central1-a}"
INSTANCE="${INSTANCE:-tbench-amd64}"
WATTLE_LABEL="${WATTLE_LABEL:-wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616}"
CODEX_LABEL="${CODEX_LABEL:-codex-compare-nonpassed-20260617}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-300}"
RUN_ONCE=0

usage() {
  cat <<EOF
Usage: $0 [--once] [--interval SECONDS]

Continuously sync GCP Terminal-Bench artifacts and regenerate per-task failure
evidence for non-passed Wattle trials.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --once)
      RUN_ONCE=1
      shift
      ;;
    --interval)
      INTERVAL_SECONDS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

log_dir="$repo_dir/runs/gcp/monitor"
mkdir -p "$log_dir"
log_file="$log_dir/monitor.log"
status_file="$log_dir/latest-status.md"

run_cycle() {
  local started
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    echo
    echo "[$started] syncing $WATTLE_LABEL and $CODEX_LABEL"
  } | tee -a "$log_file"

  ./scripts/sync_gcp_run.py \
    --project "$PROJECT" \
    --zone "$ZONE" \
    --instance "$INSTANCE" \
    --run-label "$WATTLE_LABEL" | tee -a "$log_file"

  ./scripts/sync_gcp_run.py \
    --project "$PROJECT" \
    --zone "$ZONE" \
    --instance "$INSTANCE" \
    --run-label "$CODEX_LABEL" | tee -a "$log_file"

  RUN_DIR="runs/gcp/$WATTLE_LABEL" CODEX_RUN_DIR="runs/gcp/$CODEX_LABEL" python3 - <<'PY' | tee -a "$log_file"
import json
import os
import subprocess
import sys
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
codex_run_dir = Path(os.environ["CODEX_RUN_DIR"])
snapshot = json.loads((run_dir / "analysis/incremental/snapshot.json").read_text())
tasks = sorted({trial["task"] for trial in snapshot["trials"] if trial["status"] != "passed"})
print(f"regenerating failure reports for {len(tasks)} non-passed Wattle tasks")
for task in tasks:
    subprocess.run(
        [
            sys.executable,
            "scripts/analyze_task_failure.py",
            task,
            "--run-dir",
            str(run_dir),
            "--codex-run-dir",
            str(codex_run_dir),
            "--force",
        ],
        check=True,
    )
PY

  {
    echo "# GCP TBench Monitor"
    echo
    echo "Updated: \`$(date -u +%Y-%m-%dT%H:%M:%SZ)\`"
    echo
    echo "## Wattle"
    echo
    sed -n '1,80p' "runs/gcp/$WATTLE_LABEL/analysis/incremental/summary.md"
    echo
    echo "## Codex Comparison"
    echo
    sed -n '1,80p' "runs/gcp/$CODEX_LABEL/analysis/incremental/summary.md"
  } > "$status_file"

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] wrote $status_file" | tee -a "$log_file"
}

while true; do
  run_cycle
  if [ "$RUN_ONCE" -eq 1 ]; then
    break
  fi
  sleep "$INTERVAL_SECONDS"
done
