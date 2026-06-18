# Final Reminder Targeted Evaluation

Date: 2026-06-17

Run label: `wattle-final-reminder-targeted-gcp-1attempt-20260617`

Purpose: verify whether Wattle's post-tool internal reminder reduces failures
from incomplete final validation:

```text
[system reminder]
Before choosing the next action, verify that any derived file, command, or
artifact still matches the user's required interface and preserves the meaning
of the observed inputs.

Before your next action or final answer, check whether the user's request is
actually complete. If a lightweight verification is useful, run it. If not, be
clear about what was and was not verified.
```

The run used one attempt per selected task on GCP amd64 with Wattle source
commit `fa12a99309c84fbe5a10f4c8df21e37b4b91d21f`.

## Result

Artifacts are synced locally under:

```text
runs/gcp/wattle-final-reminder-targeted-gcp-1attempt-20260617/
```

The GCP VM and attached disk were deleted after sync. `gcloud compute
instances list` and `gcloud compute disks list` both returned zero items for
the project after cleanup.

Overall result:

- Trials: 10
- Passed by verifier reward: 5 / 10
- Failed reward: 5 / 10
- Agent nonzero exits: 1 / 10
- Mean reward: 50.00%
- Input tokens: 6,087,127
- Cached input tokens: 5,560,320
- Prompt cache hit rate: 91.3%
- Output tokens: 137,927

## Task Outcomes

| Task | Baseline mean reward, 3 attempts | Reminder run reward | Error | Classification |
|---|---:|---:|---:|---|
| `build-pov-ray` | 0.667 | 1.0 | 0 | Improved final provenance/source validation |
| `configure-git-webserver` | 0.000 | 0.0 | 0 | Final-state contract misunderstood |
| `extract-moves-from-video` | 0.000 | 0.0 | 0 | Source access/semantic extraction failure |
| `financial-document-processor` | 0.333 | 1.0 | 1 | Verifier passed; Wattle crashed after moving viewed image files |
| `mcmc-sampling-stan` | 0.667 | 1.0 | 0 | Improved final artifact preservation |
| `polyglot-c-py` | 0.000 | 0.0 | 0 | Build artifacts left in single-file directory |
| `polyglot-rust-c` | 0.000 | 0.0 | 0 | Build artifacts/symlink left in single-file directory |
| `qemu-startup` | 0.667 | 1.0 | 0 | Improved service liveness validation |
| `sam-cell-seg` | 0.000 | 0.0 | 0 | Output schema check too weak |
| `winning-avg-corewars` | 0.667 | 1.0 | 0 | Improved command-shaped validation |

## What Improved

The reminder helped when the missing step was a straightforward final check of
the delivered command, artifact, or service:

- `winning-avg-corewars` passed after the agent repeatedly checked the exact
  `pmars -b -r 100 -f my_warrior.red warriors/<opponent>.red` command shape,
  preserved the required file, and confirmed opponent files were unchanged.
- `qemu-startup` passed after the agent left QEMU running and verified a fresh
  `telnet 127.0.0.1 6665` login prompt before finalizing.
- `build-pov-ray` passed after preserving official source/provenance artifacts
  and running the requested render sanity command.
- `mcmc-sampling-stan` passed after producing stable posterior mean files and
  checking the required RStan/script/model artifacts instead of overwriting a
  plausible result late.
- `financial-document-processor` passed the verifier after the agent moved all
  files, wrote `summary.csv`, and checked that `/app/documents/` was empty.

This is good signal that a lightweight post-tool reminder improves a real class
of completion failures without benchmark-specific logic.

## What Did Not Improve

The reminder did not reliably make the model derive the full verifier-visible
contract. It often validated only executable behavior, then missed final
directory shape or schema details:

- `polyglot-c-py` and `polyglot-rust-c` both verified the language runtimes but
  left generated binaries, `__pycache__`, or symlinks in `/app/polyglot`. The
  tests required the directory to contain exactly the single source file.
- `configure-git-webserver` performed end-to-end clone/push/curl validation,
  then restored the repo and web root to an empty state. The verifier's final
  HTTP request then returned 404. The issue was not lack of validation; it was
  validating a temporary state and then destroying the verifier-visible state.
- `sam-cell-seg` syntax-checked the script and grepped for key API usage, but
  did not run a representative CSV round-trip. The verifier rejected
  `coords_x`/`coords_y` because they parsed as tuples instead of flat lists.
- `extract-moves-from-video` failed for semantic/source-access reasons. The
  model could not access the YouTube video and clearly stated it could not
  fully verify the transcript. A final reminder cannot recover missing source
  evidence by itself.

## New Wattle Bug Found

`financial-document-processor` exposed a separate Wattle robustness issue:

- The agent used `view_image` on files in `/app/documents`.
- It then moved those files into `/app/invoices` and `/app/other`.
- The next provider request tried to rebuild prior image inputs by reading the
  original file paths from message history.
- Those paths no longer existed, causing:

```text
FileNotFoundError: [Errno 2] No such file or directory:
'/app/documents/2lgKzDuI4E4g.jpg'
```

The task verifier passed, but Wattle exited nonzero. Wattle should snapshot or
materialize image attachments at `view_image` time, or store data URLs/blobs in
history, so later file moves/deletes do not break subsequent provider requests.

## Product Recommendations

Priority 1: keep the post-tool reminder, but refine the behavior it asks for.

The current reminder improves outcomes, but it over-focuses the model on
command behavior. The product-level pattern we want is: validate the final
delivered state, not a temporary validation state. The wording should emphasize
that any validation artifacts must either be intentionally part of the final
deliverable or cleaned up, and that cleanup itself must be checked.

Priority 2: add a first-class "final state diff/check" habit to Wattle's
normal workflow.

This does not need benchmark-specific logic. A general agent can ask:

- What paths did I create, modify, move, or delete?
- Which of those paths are part of the user's requested interface?
- Which are temporary validation/build/cache outputs?
- After cleanup, does the final delivered directory/file/service/schema still
  satisfy the request?

This would directly target the polyglot and git-server failures.

Priority 3: make validation use the same consumer-visible interface as the
final answer.

The agent should avoid validating from helper paths or temporary states when
the user specified an exact path, command, port, or schema. For example:

- validate `/app/polyglot` contains exactly the intended source file after
  compile tests
- validate the web server still serves the requested file after any repo/root
  cleanup
- validate generated CSV fields parse to the intended JSON/list/scalar types

Priority 4: fix attachment lifetime in Wattle.

Viewed files must remain available to future provider requests even if the
workspace file is moved or deleted. This is a core product issue, not a
Terminal-Bench-specific issue.

Priority 5: treat "cannot verify" as a useful final state, not a hidden pass.

The video task behaved correctly in that it disclosed the verification gap, but
still produced a low-confidence answer. In everyday use, Wattle should make the
confidence boundary sharper when source evidence is unavailable: preserve the
best effort artifact if useful, but state that correctness is unverified and
why.

## Bottom Line

The lightweight post-tool reminder is worth keeping. It likely helped 4-5 of
the 10 targeted cases pass or improve. It is not sufficient for failures where
the model validates the wrong state, leaves temporary artifacts behind, checks
only syntax instead of schema, or lacks the source evidence needed for semantic
recovery.

The next highest-value improvement is not a benchmark-specific stop hook. It is
general final-state discipline: after validation, check the actual delivered
paths, services, schemas, and cleanup state that the user or downstream
consumer will observe.
