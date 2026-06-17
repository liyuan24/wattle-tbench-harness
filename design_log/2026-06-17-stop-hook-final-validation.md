# Stop Hook Final Validation Design

Date: 2026-06-17

## Context

Terminal-Bench failures show a recurring Wattle behavior: the model often
announces completion after making plausible progress, but before doing the
final state audit that would catch mismatches with the task contract. Examples
include missing expected files, using the wrong upstream artifact, not running
the verifier-shaped command, or reporting a partial result as complete.

Prompt-only guidance is not enough. It can ask the model to validate before
finishing, but it does not create a lifecycle checkpoint at the exact moment
the model is about to end the turn. A Stop hook gives the harness that
checkpoint without hard-coding task-specific rules into Wattle's normal agent
loop.

The goal is not to overfit to individual failed tasks. The goal is a general
mechanism that lets Wattle or the harness ask, "is this turn really ready to
end?" and, if not, continue the same turn with grounded feedback.

## Codex Reference Behavior

Codex treats Stop hooks as lifecycle hooks, not as model instructions.

The important split is:

- Codex core owns orchestration: when to call hooks, how to pass context, how
  to parse hook output, and how to continue the turn.
- The configured hook command owns judgment: whether the agent should stop,
  continue, or be blocked with a continuation prompt.

In the inspected local Codex source, Stop hooks are triggered only when the
model would otherwise end the turn. If there is still a normal follow-up, such
as a tool call, the Stop hook is not the thing driving continuation.

When a Stop hook blocks, Codex converts the hook's reason into a synthetic
user-side hook prompt, records it in the conversation history, marks
`stop_hook_active = true`, and continues the same turn loop. The model then
sees the hook feedback and can run more tools or revise its final answer.

If no Stop hook is configured, Stop hook execution is a no-op. The default
outcome is no stop request, no block, and no continuation prompt.

## Hook Framework

Wattle should model hooks as a small framework rather than a single hard-coded
audit rule. The registry should be the source of truth for available hook
kinds, so future hook types can be added without reshaping the agent loop.

Initial scope:

- `Stop`: runs when the model has produced a response with no tool request and
  the harness is about to accept the final assistant answer.

Future-compatible shape:

- A hook registry exposes a generic `run(request)` API.
- Event-specific helpers can construct typed requests, for example
  `StopHookRequest`.
- Event-specific parsers convert hook process output into a common hook
  outcome.
- The agent loop consumes outcomes uniformly: continue, stop, block, or ignore
  failed hook output.

The core Wattle loop should not hard-code "did the model run pytest" or
"does the answer mention success" checks. Those policies belong in the Stop
hook implementation, because the right audit can vary by evaluation harness,
task family, and operating mode.

## Stop Hook Trigger

The Stop hook should run at the end-turn boundary:

1. The model response has no requested tool call.
2. The agent loop would normally finalize the assistant message.
3. The hook registry has an enabled `Stop` hook for the current run.
4. Wattle builds a Stop hook request and invokes the hook.

The hook should not run after every tool result. Post-tool hooks can be added
later if needed, but Stop is specifically the last gate before accepting the
assistant's final answer.

The Stop hook request should include enough context for a policy command to
make a grounded decision:

- run id, task id, attempt id, and turn id
- working directory and container/app directory
- transcript path or serialized recent transcript
- last assistant message
- model name and provider
- remaining deadline or timeout context
- paths to task prompt, tests, and known artifacts when available
- whether this Stop hook is already active for the current turn

The `stop_hook_active` flag is important. It lets a hook avoid repeatedly
blocking with the same generic message after the model has already been told
to continue.

## What The Stop Hook Should Do

The first Wattle Terminal-Bench Stop hook should be an evaluation-aware final
audit, not a task-specific oracle.

It should inspect the task context and transcript, then decide whether the
model's final answer is acceptable to pass through. Useful checks include:

- Did the model perform a final verification action after the last meaningful
  file/system change?
- Did it run the task's available test script, verifier-like command, or an
  equivalent direct check when such a check is discoverable?
- If verification failed, did it fix the issue and rerun verification?
- Does the final assistant message claim success while the latest tool output
  shows failure, timeout, missing files, or incomplete execution?
- Are expected output files or directories present when the task prompt or
  tests make them obvious?
- Did the model stop because of time pressure without producing the required
  artifact?

The hook should prefer grounded continuation messages over broad advice. A
good block reason tells the model exactly what is missing and what evidence
it should collect next.

Example continuation prompt:

```text
The turn is about to end, but the transcript does not show a verifier-shaped
check after the last file change. Run the task test script or an equivalent
direct validation now. If it fails, fix the failure and rerun it before giving
the final answer.
```

For Terminal-Bench, the hook can use known harness structure to be more
specific when safe:

```text
The final answer claims the task is complete, but `/tests/test_outputs.py`
has not been run after the last change. Copy or use the available tests in
the task container, run the test command, and only finish after the result is
consistent with the task requirements.
```

The hook should not require the user to opt in per task. It is part of the
evaluation harness behavior.

## Decision Contract

The Stop hook should return a mechanical decision that the harness can enforce.

Proposed minimal output:

```json
{
  "decision": "block",
  "reason": "Run the task verifier after the last change; the transcript only shows a pre-fix failure."
}
```

Other outcomes:

```json
{
  "decision": "allow"
}
```

```json
{
  "decision": "stop",
  "reason": "The hook intentionally terminates the turn."
}
```

The harness should treat invalid hook output as hook failure, not as a task
failure. A failed hook should be logged and ignored for that turn unless the
run is explicitly configured to fail closed.

The block reason must be non-empty. A block without actionable feedback should
not be injected into the model context.

## Harness Semantics

The harness should use the Stop hook decision as an end-turn control signal:

- `allow`: accept the assistant answer and end the turn normally.
- `block`: append a synthetic hook prompt to the conversation and continue the
  same agent turn.
- `stop`: end the turn immediately according to the hook's stop reason.
- `hook_error`: record diagnostics and continue according to configured
  fail-open or fail-closed policy.

For the initial Terminal-Bench harness, fail-open is safer while the hook is
being developed. It avoids making the benchmark fragile because of hook bugs.
The run artifacts must still record hook errors prominently so they are not
silent.

When blocked, the harness should:

1. Persist a hook event with status `blocked`, command/output metadata, and
   the reason.
2. Add the reason as a model-visible user-side hook message.
3. Continue the same attempt without resetting the transcript or losing tool
   state.
4. Set `stop_hook_active = true` for the next Stop hook request in that turn.
5. Cap repeated Stop blocks to prevent infinite loops.

The model should not see hidden policy details or raw harness internals unless
they are needed to act. It should see the actionable continuation prompt.

## Why This Belongs In The Harness

The Terminal-Bench harness has context Wattle core should not assume:

- where tests live
- how Harbor copies task files
- how attempts, artifacts, and transcripts are stored
- how to interpret a task deadline
- how to collect verifier and oracle-derived signals for analysis

Wattle core should provide the hook lifecycle and transcript continuation
mechanism. The Wattle Terminal-Bench harness should provide the first Stop
hook policy because the policy is benchmark-specific.

This split keeps the improvement general: Wattle becomes capable of lifecycle
audits, while Terminal-Bench gets a concrete final validation hook that is
grounded in task evidence.

## Expected Impact

The Stop hook should primarily improve failures where Wattle had enough
information and time to pass but ended early. It is not expected to solve
failures caused by missing dependencies, impossible architecture constraints,
or tasks that need more wall-clock time than the harness allows.

The highest-value target is the common failure pattern where the transcript
contains enough evidence to say "not done yet" before the assistant final
answer is accepted.

Success should be evaluated by:

- pass-rate lift on full Terminal-Bench 2.0 runs
- lower rate of final answers after stale or failed verification
- lower rate of missing expected output artifacts
- low incidence of Stop hook false positives causing wasted turns
- bounded added latency and token usage

## Open Design Questions

1. Should the first Stop hook be a deterministic transcript analyzer, an LLM
   judge, or a hybrid?
2. What maximum number of Stop blocks should be allowed per turn?
3. Should the hook be allowed to run commands inside the task container, or
   should it only inspect transcripts and artifacts?
4. How should oracle logs be made available for offline analysis without
   leaking oracle-specific hints into scored Wattle attempts?
5. Should fail-closed mode be available only for development runs, or also for
   official evaluations once the hook is stable?
