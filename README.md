# Wattle Terminal-Bench Harness

Harbor / Terminal-Bench 2.0 harness for evaluating
[Wattle](https://github.com/liyuan24/wattle).

This repo intentionally uses Harbor, not the legacy `tb run
terminal-bench-core==0.1.1` path. The runner invokes:

```bash
harbor run -d terminal-bench@2.0 --agent-import-path wattle_harbor_agent:WattleAgent
```

## Setup

```bash
cd /home/liyuan/repos/wattle-tbench-harness
./setup.sh
```

Harbor should be available either from this repo's `.venv/bin/harbor` or from
`~/.local/bin/harbor`.

Before full Docker evaluations, apply and verify the Harbor upload-dir patch:

```bash
python scripts/patch_harbor_upload_dir.py
python scripts/check_harbor_patch.py
```

The patch makes Harbor copy directory contents into the task environment. This
prevents verifier-test path corruption when an agent creates `/tests`.

`--wattle-provider-request-timeout-sec` sets both Wattle's SDK request timeout
and Wattle's stream-idle timeout by default. Use
`--wattle-stream-idle-timeout-sec` only when those should differ.

## Auth

The Harbor adapter can use either a Wattle auth file or provider API key
environment variables.

Default auth file lookup:

```text
~/.wattle/auth.json
~/.willow/auth.json
```

Explicit auth path:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --wattle-auth-path /home/liyuan/.willow/auth.json
```

Environment alternatives:

```bash
export DEEPSEEK_API_KEY=...
export KIMI_API_KEY=...
export MINIMAX_API_KEY=...
export OPENAI_API_KEY=...
export CODEX_OAUTH_TOKEN=...
```

To save current env auth for repeated shell use:

```bash
python scripts/export_auth_env.py ~/.wattle-tbench-harness.env
source ~/.wattle-tbench-harness.env
```

## One-Command Evaluation

Run the whole Terminal-Bench 2.0 suite headlessly for a chosen model:

```bash
cd /home/liyuan/repos/wattle-tbench-harness
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --n-attempts 1 \
  --n-concurrent 2 \
  --force-build \
  --wattle-provider-request-timeout-sec 120 \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json
```

Run detached in tmux:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --n-attempts 1 \
  --n-concurrent 2 \
  --force-build \
  --wattle-provider-request-timeout-sec 120 \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json \
  --tmux
```

The runner records:

- `manifest.json`: dataset, Wattle commit, harness commit, and arguments.
- `commands/*.json`: exact Harbor command.
- `logs/*.log`: stdout/stderr from Harbor.
- `jobs/<job-name>/`: Harbor job output.
- `reports/`: aggregate, per-task, and per-trial reports generated from Harbor
  `result.json` files.

## Focused Runs

Run one task headlessly by Terminal-Bench task name:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --include-task-name adaptive-rejection-sampler \
  --n-attempts 1 \
  --n-concurrent 1 \
  --force-build
```

`--task-id` is accepted as an alias for `--include-task-name` for convenience.

Run the first `N` tasks after Harbor filtering:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --n-tasks 10 \
  --n-attempts 1 \
  --n-concurrent 2
```

Dry-run command generation:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --include-task-name break-filter-js-from-html \
  --dry-run
```

## TUI Investigation

Run one task in Wattle's native TUI:

```bash
./run_tui_task.py \
  --task-name break-filter-js-from-html \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json \
  --attach
```

The launcher downloads the Terminal-Bench task if needed, starts Harbor's
interactive Docker environment, installs the Wattle agent, and queues the
interactive command inside the task shell:

```bash
wattle --provider deepseek --model deepseek-v4-pro --yolo --thinking --effort high "$task_prompt"
```

The prompt comes from `/task/instruction.md` after the Docker environment is
built, so the first message is populated inside the Wattle TUI for the exact
task container being investigated. It does not use `-p/--print`, which is
Wattle's headless mode.

Use a local task checkout instead of downloading:

```bash
./run_tui_task.py \
  --task-name break-filter-js-from-html \
  --task-path /tmp/harbor-tasks/break-filter-js-from-html \
  --model deepseek/deepseek-v4-pro \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json \
  --attach
```

From the same interactive environment, run the verifier manually when ready:

```bash
bash /tests/run-tests.sh
```

For post-run browsing, use Harbor's viewer:

```bash
harbor view runs/<run-label>/jobs --jobs
```

## Result Reports

Generate reports for any Harbor result root:

```bash
python scripts/generate_reports.py runs/<run-label>
```

Important report files:

- `reports/aggregate.json`
- `reports/summary.md`
- `reports/per_task.csv`
- `reports/per_trial.csv`

## Current DeepSeek Command

The expected DeepSeek diagnostic command is:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --n-attempts 1 \
  --n-concurrent 2 \
  --force-build \
  --wattle-provider-request-timeout-sec 120 \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json \
  --tmux
```
