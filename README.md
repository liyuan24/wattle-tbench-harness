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

Before full Docker evaluations, apply and verify the Harbor patches:

```bash
python scripts/patch_harbor_upload_dir.py
python scripts/patch_harbor_agent_timeout.py
python scripts/check_harbor_patch.py
```

The upload-dir patch makes Harbor copy directory contents into the task
environment. This prevents verifier-test path corruption when an agent creates
`/tests`. The agent-timeout patch passes Harbor's computed per-task agent
timeout to installed agents, which lets Wattle tell the model the remaining
wall-clock budget.

Harbor owns Terminal-Bench task deadlines and container cleanup. Wattle provider
timeout flags are optional diagnostics; omit them for the default benchmark path.
The harness computes `WATTLE_RUN_DEADLINE_EPOCH_MS` from each task's
`[agent].timeout_sec` immediately before Wattle starts, so Wattle can tell the
model the remaining wall-clock budget without changing the task prompt.

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

Run one task in a container-backed interactive TUI. Wattle remains the default
agent:

```bash
./run_tui_task.py \
  --task-name break-filter-js-from-html \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --source-dir /home/liyuan/repos/wattle
```

Run the same task with Codex CLI directly instead of Wattle:

```bash
./run_tui_task.py \
  --agent codex \
  --task-name break-filter-js-from-html \
  --model gpt-5.5
```

The launcher downloads the Terminal-Bench task if needed, builds
`environment/Dockerfile` or uses `environment.docker_image`, reads the task
instruction, and starts the selected agent inside the task container with
`/app` as the working directory. For `--agent codex`, only Codex auth/config are
copied into the container.

Use a local task checkout instead of downloading:

```bash
./run_tui_task.py \
  --task-name break-filter-js-from-html \
  --task-path /tmp/harbor-tasks/break-filter-js-from-html \
  --model deepseek/deepseek-v4-pro \
  --source-dir /home/liyuan/repos/wattle
```

This TUI launcher is for human inspection. Use the Harbor-backed harness when
you need the verifier or scored run behavior.

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

## Benchmark Results

### DeepSeek V4 Pro, high effort, 2026-06-13

Run label:
`harbor-wattle-deepseek-v4-pro-high-20260613-harbor-deadlines`

Command shape:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --n-attempts 1 \
  --n-concurrent 2 \
  --force-build \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json \
  --run-label harbor-wattle-deepseek-v4-pro-high-20260613-harbor-deadlines \
  --tmux
```

Evaluated commits:

- Wattle: `3d1927b2670c604dee796d7809e6e25a9f0020d4`
- Harness: `dbf61d988509330f6400e40484423dd74f9f49cb`

Results:

- Dataset: `terminal-bench@2.0`
- Trials: 89
- Reward 1.0: 53
- Reward 0.0: 34
- Agent timeouts without verifier reward: 2
- Agent timeout exceptions total: 7
- Mean reward: 59.55%
- Runtime: 6h 41m 18s
- Reports:
  `runs/harbor-wattle-deepseek-v4-pro-high-20260613-harbor-deadlines/reports`

## Current DeepSeek Command

The expected DeepSeek diagnostic command is:

```bash
./run_tbench.py \
  --model deepseek/deepseek-v4-pro \
  --effort high \
  --n-attempts 1 \
  --n-concurrent 2 \
  --force-build \
  --source-dir /home/liyuan/repos/wattle \
  --wattle-auth-path /home/liyuan/.willow/auth.json \
  --tmux
```

## Current Codex Command

Run one scored Terminal-Bench task with Codex CLI directly:

```bash
./run_tbench.py \
  --agent codex \
  --model gpt-5.5 \
  --include-task-name train-fasttext \
  --n-attempts 1 \
  --n-concurrent 1 \
  --force-build
```

Run a full scored suite with Codex CLI directly:

```bash
./run_tbench.py \
  --agent codex \
  --model gpt-5.5 \
  --n-attempts 1 \
  --n-concurrent 2 \
  --force-build \
  --tmux
```
