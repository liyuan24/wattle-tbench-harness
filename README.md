# Wattle Terminal-Bench Harness

External Terminal-Bench harness for evaluating
[Wattle](https://github.com/liyuan24/wattle) and OpenAI Codex without modifying
the Wattle source tree.

The Wattle adapter installs a source archive into each task container, runs the
`wattle` CLI, and records token usage from persisted Wattle session JSONL files.

## Install

```bash
cd /home/liyuan/repos/wattle-tbench-harness
./setup.sh
```

For Codex-only runs:

```bash
./setup-codex.sh
```

## Pi Test Directory Patch

For Harbor / Terminal-Bench 2.0 runs, apply Pi's patch to Harbor's Docker
`upload_dir` behavior before starting evals. Without the patch, Harbor can
mis-copy the verifier tests folder when the agent creates `/tests` inside the
trial container. The patch changes Docker copy behavior to copy directory
contents with `/.` instead of copying the source directory itself.

In the Harbor adapter repo this is checked with:

```bash
python scripts/patch_harbor_upload_dir.py
python scripts/check_harbor_patch.py
```

Run this once in the Python environment that provides `harbor` before launching
the full Terminal-Bench jobs.

## Running Wattle Evals

Run Wattle on all Terminal-Bench core tasks with this harness:

```bash
cd /home/liyuan/repos/wattle-tbench-harness
./run_tbench.py \
  --agent wattle \
  --provider minimax \
  --model MiniMax-M2.7 \
  --effort high
```

Use a specific provider/model by changing `--provider` and `--model`:

```bash
./run_tbench.py \
  --agent wattle \
  --provider deepseek \
  --model deepseek-v4-pro \
  --effort high \
  --n-attempts 5 \
  --n-concurrent 2
```

Run OpenAI Codex directly for comparison:

```bash
./run_tbench.py \
  --agent codex \
  --model gpt-5.5 \
  --effort high
```

Run a single task:

```bash
./run_tbench.py \
  --agent wattle \
  --task-id hello-world \
  --provider openai_codex \
  --model gpt-5.5 \
  --effort none
```

Run either command in a detached tmux session:

```bash
./run_tbench.py \
  --agent wattle \
  --task-id hello-world \
  --provider openai_codex \
  --model gpt-5.5 \
  --effort none \
  --tmux
```

The command returns after creating the tmux session. Reattach with the printed
`tmux attach -t ...` command; the run continues if the SSH session disconnects.

`--effort none` disables Wattle thinking and leaves Codex reasoning effort at
the config default. Any other effort (`low`, `medium`, `high`, `xhigh`, `max`)
is passed to the agent.

`--provider` applies only to Wattle. Codex always uses the Codex/OpenAI auth
path and only needs `--model` and `--effort`.

## Full Eval Results

These results are from the full Harbor / Terminal-Bench 2.0 run started at
`2026-05-25T17:32:16Z`, with `n_attempts=5` and `n_concurrent=2`.

Terminal-Bench test commit:
`69671fbaac6d67a7ef0dfec016cc38a64ef7a77c`

Wattle commit:
`4224c26cd7cc5439be4c232313ebbb50026e0528`

Harness commit:
`f92fcc59a19ba6e705fc966469858cd7d7bb73f3`

The Terminal-Bench leaderboard reports `Accuracy` as a percentage with an
uncertainty term. This table follows that convention: mean task pass rate
`+- 1.96 * standard_error`, where the standard error is computed across the 89
task-level pass rates from the 5 attempts per task.

| Provider | Model | Trials | Accuracy | Input tokens | Output tokens | Cache tokens |
|---|---|---:|---:|---:|---:|---:|
| `codex` | `gpt-5.5` | 445 | 68.3% +- 7.8 | 134,915,145 | 3,959,401 | 123,100,672 |
| `deepseek` | `deepseek-v4-pro` | 445 | 37.5% +- 8.6 | 134,835,223 | 2,817,532 | 130,606,208 |

### DeepSeek Single-Attempt Diagnostic Run

This run was started at `2026-06-12T17:49:49` against
`terminal-bench-core==0.1.1`, with `n_attempts=1`, `n_concurrent=2`, Wattle
provider `deepseek`, model `deepseek-v4-pro`, and effort `high`.

Run ID:
`20260612-174948-wattle-deepseek-deepseek-v4-pro-high`

Wattle commit:
`c95a9662df1994f15f3f8173df1cb78e06442331`

The run completed all 80 tasks with harness exit status `0`.

| Provider | Model | Trials | Resolved | Accuracy | Sessions with usage | Exception summary |
|---|---|---:|---:|---:|---:|---|
| `deepseek` | `deepseek-v4-pro` | 80 | 33 | 41.25% | 61 / 80 | `MalformedToolCallError`: 1 |

Failure-mode summary: `agent_timeout`: 11, `unknown_agent_error`: 8,
`test_timeout`: 2, `parse_error`: 1, `agent_installation_failed`: 1.

## Run IDs

The runner creates a timestamped run id by default:

```text
YYYYMMDD-HHMMSS-wattle-minimax-MiniMax-M2.7-high
YYYYMMDD-HHMMSS-codex-gpt-5.5-high
```

Terminal-Bench uses this as the run directory name under `tb-runs/`, embeds it
in trial names, and records it in `results.json`. The timestamp keeps repeated
runs of the same config separate.

## Output

Each invocation creates a batch directory under:

```text
/home/liyuan/repos/wattle-tbench-harness/runs/
```

Important files:

- `summary.md`: batch-level run table.
- `commands/*.json`: exact `tb run` command.
- `logs/*.log`: stdout/stderr from `tb run`.
- `tb-runs/<run-id>/results.json`: raw Terminal-Bench result.
- `analysis/<case>/summary.md`: pass rate and aggregate timing/token stats.
- `analysis/<case>/tasks.csv`: per-task pass/fail, durations, and token metrics.

Inside each Terminal-Bench trial:

```text
<run-dir>/<task-id>/<trial-name>/agent-logs/wattle-sessions/*.jsonl
<run-dir>/<task-id>/<trial-name>/agent-logs/codex-events.jsonl
<run-dir>/<task-id>/<trial-name>/agent-logs/codex-output.log
```

## Metrics

Timing comes from Terminal-Bench `results.json`:

- `agent_duration_seconds`: `agent_ended_at - agent_started_at`
- `trial_duration_seconds`: `trial_ended_at - trial_started_at`
- `test_duration_seconds`: `test_ended_at - test_started_at`

Wattle token usage comes from session JSONL assistant messages.

Codex token usage is parsed from `codex exec --json` `turn_completed` events.
Those events expose cumulative thread totals, so the analyzer uses the latest
usage event for the task. If JSON usage is unavailable, the analyzer falls back
to the Codex human footer:

```text
tokens used
38,366
```

That footer is Codex's blended/billable-style total:

```text
(input_tokens - cached_input_tokens) + output_tokens
```

The analyzer reports multiple token columns so we can choose later:

- `input_tokens`
- `cached_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `billable_input_tokens`: `input_tokens - cached_tokens`
- `raw_total_tokens`: `input_tokens + output_tokens`
- `billable_total_tokens`: `billable_input_tokens + output_tokens`
- `codex_footer_billable_total_tokens`: fallback footer value when JSON usage is unavailable
- `final_turn_input_tokens`
- `max_turn_input_tokens`

## Auth

Wattle:

- Preferred: `~/.wattle/auth.json`
- Fallback for `openai_codex`: `~/.codex/auth.json`, converted to Wattle's
  `{"openai": {"oauth": ...}}` shape inside the container.
- DeepSeek, Kimi, and MiniMax keys should be in `~/.wattle/auth.json`.

Codex:

- Uses `~/.codex/auth.json`
- Copies optional `~/.codex/config.toml`
