# Wattle GPT-5.5 Train-FastText Failure Analysis

Date: 2026-06-16

Task: `train-fasttext`

Main run inspected:
`runs/wattle-gpt-5-5-contract-checkpoint-train-fasttext-3x-20260616`

Related Wattle runs inspected:

- `runs/wattle-gpt-5-5-operational-context-train-fasttext-20260615*`
- `runs/wattle-gpt-5-5-silent-checkpoint-train-fasttext-20260616`
- `runs/wattle-gpt-5-5-validation-literal-tiny-train-fasttext-20260616`
- `runs/wattle-gpt-5-5-validation-resource-discipline-train-fasttext-20260616`

Oracle/Codex run inspected:
`runs/codex-gpt-5-5-train-fasttext-inspect-20260616`

The Codex run is not a completed oracle. Its job metadata still reports one
running trial and no verifier output. I used its JSONL only as a partial
behavioral comparison, not as pass/fail evidence.

## Current Result

No local Wattle GPT-5.5 `train-fasttext` run passed the private verifier.

Latest 3-attempt Wattle run:

| Trial | Outcome | Evidence |
|---|---:|---|
| `train-fasttext__SBj4SyX` | exception | top-level Wattle command exit 137; no reward file |
| `train-fasttext__voKkH3b` | exception | top-level Wattle command exit 137; no reward file |
| `train-fasttext__VJHVwMg` | verifier failure | public self-check passed, private verifier failed at `0.619625 > 0.62` |

The verifier failure is important: Wattle produced `/app/model.bin`, verified it
locally on the public test file at `0.6244`, and reported success. Harbor's
private verifier then scored it 0 because private accuracy was `0.619625`, just
below the strict `> 0.62` threshold.

## Failure Pattern

### 1. Thin Validation Margins

Wattle treated a public/proxy validation score barely over the requested
threshold as sufficient. In the latest complete trial, the model had:

- public/proxy accuracy: `0.6244`
- private verifier accuracy: `0.619625`
- required private condition: `accuracy > 0.62`

This is not a label-format or output-path failure. The model size test passed,
and the private verifier loaded `/app/model.bin`. The gap is that Wattle did
not account for proxy-to-private variance.

### 2. Expensive Exploration Consumes the Run

Across failed traces, Wattle repeatedly spent time on:

- installing compiler/toolchain dependencies,
- building `fasttext`,
- converting large data files,
- running long foreground training jobs,
- launching extra hyperparameter trials after a near-sufficient candidate.

Some runs reached a viable-ish artifact and then spent remaining budget chasing
small improvements. Other runs were killed or timed out before finalizing a
scored artifact.

### 3. Deadline Context Exists But Is Too Weak

The harness exports `WATTLE_RUN_DEADLINE_EPOCH_MS`, and Wattle injects a
deadline notice. The traces show the model still starts or continues long
commands late in the run. The deadline notice is advisory; there is no runtime
guard that says, for example:

- this command has already used 600 seconds,
- only N minutes remain,
- a required artifact exists but has not been verifier-style checked,
- stop exploration and preserve the best known artifact.

### 4. Long Foreground Commands Hide Decision Points

Training commands run as foreground `bash` calls. While they run, the model
cannot adapt. When they time out or are killed, the trace often contains only
the next provider request or a top-level exit 137, not a clean "save best known
artifact, verify, final" path.

### 5. Reports Do Not Surface Root Cause

The report says `score_reward: 0.0`, `AgentTimeoutError`, or
`NonZeroAgentExitCodeError`, but the actionable cause is buried in JSONL or
`verifier/ctrf.json`. For this task, the most important line is:

```text
assert 0.619625 > 0.62
```

That is not visible in the batch summary.

## Harness/Wattle Gaps

These are general gaps, not train-fasttext-specific fixes.

1. Wattle needs a general validation-margin rule for tasks that mention private
   tests, hidden data, stochastic evaluation, benchmarks, or same-distribution
   generalization.

2. Wattle needs stronger deadline-aware behavior around expensive commands:
   checkpoint current best outputs before optional exploration, reserve time for
   final validation, and avoid starting commands that cannot fit in the
   remaining budget.

3. Wattle's command tool should make timeout clamping and elapsed time more
   salient to the next model turn.

4. The harness should summarize verifier failure traces and last agent actions
   automatically so failure analysis does not require ad hoc JSONL spelunking.

5. The harness should distinguish "agent produced an artifact but verifier
   failed" from "agent died before artifact/verifier" in reports.

## Improvement Plan

### P0: Reporting Improvements

Add post-run failure summarization to `scripts/generate_reports.py`.

For each failed trial, extract:

- exception type and top-level exit status,
- last assistant message,
- last tool call command summary,
- last tool result status: success, timeout, nonzero, killed,
- verifier failing test names and assertion snippets from `ctrf.json`,
- artifact facts for common required outputs when discoverable from verifier or
  task prompt.

This is simple, low-risk, and immediately improves future analysis across all
tasks.

### P0: Validation Margin Guidance

Add a short, general prompt rule to Wattle:

```text
When the real evaluator is private, hidden, stochastic, or same-distribution
withheld data, do not treat a proxy score barely above the threshold as enough.
Aim for a practical margin when time/resources allow. If only a thin margin is
available, keep the best artifact but continue improving only if the remaining
deadline leaves time to revalidate and finalize.
```

This avoids overfitting to fastText while addressing the observed private/public
gap.

### P0: Best Artifact First

Add general guidance and runtime status for required artifacts:

- once an artifact satisfies known hard constraints, copy/save it to the final
  required path immediately;
- optional improvement trials must not delete or replace the current best unless
  the new candidate is validated;
- before final answer, re-stat and revalidate the final path.

This is general for model files, binaries, configs, generated datasets, trained
weights, and build outputs.

### P1: Deadline-Aware Command Guard

Before dispatching a foreground command whose requested timeout is large, Wattle
should compare requested timeout with `RunDeadline.remaining_seconds()`.

Provider-visible warning after tool result or before the next turn:

```text
Runtime status:
- Last command used 588s and timed out.
- About 11 minutes remain.
- `/app/model.bin` exists and was last validated at 0.6209 on a proxy test.
```

The tool does not need to block the command. It should make the tradeoff
explicit to the model and encourage finalization when the budget is tight.

### P1: Shell Tool Timeout Transparency

The `bash` tool clamps foreground commands to 600 seconds. The model usually
does not reason about that limit. Add the max timeout to the tool description
and include both requested and effective timeout in timeout results.

This is general and helps any task with builds, training, downloads, or long
tests.

### P1: Optional Monitor Pattern For Long Jobs

When a command is likely to run for many minutes, encourage this pattern:

1. start it with output redirected to a log,
2. monitor progress compactly,
3. preserve a kill/fallback point,
4. checkpoint artifacts after each successful candidate.

This should remain guidance, not an automatic rewrite of shell commands.

### P2: Benchmark Context Injection

The harness can optionally append a short benchmark context wrapper around the
task instruction:

```text
Benchmark context:
- The final answer is judged by a verifier after the agent exits.
- If the task mentions private/hidden tests or same-distribution data, public
  checks are proxies and need margin.
- Save required outputs at the exact requested paths before optional
  exploration.
- Leave enough time for final validation and exit cleanly.
```

Keep this behind a harness flag first. It is general Terminal-Bench context, not
task-specific advice.

## What Not To Do

Do not hard-code the successful fastText hyperparameters into Wattle or the
harness.

Do not add task-name-specific prompts.

Do not make Wattle always optimize for larger margins; some tasks have expensive
or unavailable validation. The rule should be "seek margin when the evaluator is
hidden and time/resources allow."

Do not rerun already-passing tasks just to gather more data. The useful next
test is one focused rerun after implementing the P0 changes.

## Suggested Next Validation

After P0 changes:

1. Run one focused `train-fasttext` Wattle GPT-5.5 attempt.
2. Verify the report includes the private assertion if it fails.
3. Check whether Wattle either passes or exits with a clearly preserved best
   artifact and explicit thin-margin caveat.
4. Then test on one unrelated task with hidden/private validation to confirm the
   margin guidance is general.
