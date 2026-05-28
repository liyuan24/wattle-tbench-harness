# Prompt Caching Investigation

Date: 2026-05-22

Task used for comparison: `organization-json-generator`

All Wattle runs used the same Terminal-Bench harness shape:

```bash
./run_tbench.py --agent wattle --task-id organization-json-generator --effort high
```

The compared rows were:

- Wattle / OpenAI Codex: `openai_codex/gpt-5.5`
- Wattle / DeepSeek: `deepseek/deepseek-v4-pro`
- Wattle / Kimi: `kimi/kimi-k2.6`
- Codex agent / OpenAI Codex: `gpt-5.5`

## Summary

Wattle/OpenAI Codex showed unexpectedly weak prompt caching compared with both
Wattle/DeepSeek and Wattle/Kimi, even though they all ran through the same
Terminal-Bench harness.

The Wattle/OpenAI Codex cache ratio looks like a real cache-hit issue, not a
harness math issue.

## Aggregate Results

| Agent | Provider | Model | Pass | Agent time | Input | Cached | Output | Raw total | Billable total | Cached / Input |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Wattle | Kimi | `kimi-k2.6` | 1/1 | 54.80s | 72,868 | 53,248 | 2,682 | 75,550 | 22,302 | 73.08% |
| Wattle | DeepSeek | `deepseek-v4-pro` | 1/1 | 81.33s | 46,009 | 36,736 | 3,499 | 49,508 | 12,772 | 79.85% |
| Wattle | OpenAI Codex | `gpt-5.5` | 1/1 | 103.29s | 110,237 | 24,576 | 3,342 | 113,579 | 89,003 | 22.29% |
| Codex agent | OpenAI Codex | `gpt-5.5` | 1/1 | 158.00s | 272,605 | 260,864 | 4,672 | 277,277 | 16,413 | 95.69% |

Definitions:

- `Raw total = input + output`
- `Billable input = input - cached`
- `Billable total = billable input + output`
- `Cached / Input = cached / input`

## Per-Turn Cache Breakdown

The aggregate Wattle/OpenAI Codex number is not just distorted by having more
turns. Its per-turn cache hit behavior is inconsistent, including several late
turns with zero cached input.

### Wattle / OpenAI Codex

| Turn | Input | Cached | Cached / Input | Output | Notes |
|---:|---:|---:|---:|---:|---|
| 1 | 3,271 | 0 | 0.0% | 152 | first turn |
| 2 | 3,436 | 1,536 | 44.7% | 33 |  |
| 3 | 3,510 | 1,536 | 43.8% | 51 |  |
| 4 | 3,602 | 3,072 | 85.3% | 82 | best early cache hit |
| 5 | 5,513 | 0 | 0.0% | 635 | cache miss after prompt growth |
| 6 | 6,161 | 1,536 | 24.9% | 1,468 |  |
| 7 | 8,635 | 1,536 | 17.8% | 80 |  |
| 8 | 8,728 | 0 | 0.0% | 35 | late miss |
| 9 | 8,787 | 0 | 0.0% | 22 | late miss |
| 10 | 11,099 | 8,704 | 78.4% | 26 | good hit |
| 11 | 11,554 | 5,120 | 44.3% | 130 |  |
| 12 | 11,697 | 0 | 0.0% | 308 | late miss |
| 13 | 12,036 | 0 | 0.0% | 159 | late miss |
| 14 | 12,208 | 1,536 | 12.6% | 161 | final turn |

Total: 110,237 input, 24,576 cached, 22.29% cached.

### Wattle / DeepSeek

| Turn | Input | Cached | Cached / Input | Output |
|---:|---:|---:|---:|---:|
| 1 | 4,199 | 768 | 18.3% | 126 |
| 2 | 4,371 | 4,224 | 96.6% | 164 |
| 3 | 6,298 | 4,480 | 71.1% | 2,040 |
| 4 | 9,472 | 8,320 | 87.8% | 68 |
| 5 | 9,585 | 9,344 | 97.5% | 65 |
| 6 | 12,084 | 9,600 | 79.4% | 1,036 |

Total: 46,009 input, 36,736 cached, 79.85% cached.

### Wattle / Kimi

| Turn | Input | Cached | Cached / Input | Output |
|---:|---:|---:|---:|---:|
| 1 | 3,386 | 0 | 0.0% | 115 |
| 2 | 3,535 | 2,048 | 57.9% | 40 |
| 3 | 3,715 | 2,048 | 55.1% | 53 |
| 4 | 5,048 | 2,048 | 40.6% | 70 |
| 5 | 5,841 | 4,096 | 70.1% | 470 |
| 6 | 6,330 | 4,096 | 64.7% | 1,211 |
| 7 | 8,493 | 6,144 | 72.3% | 40 |
| 8 | 8,563 | 8,192 | 95.7% | 203 |
| 9 | 8,825 | 8,192 | 92.8% | 62 |
| 10 | 9,492 | 8,192 | 86.3% | 129 |
| 11 | 9,640 | 8,192 | 85.0% | 289 |

Total: 72,868 input, 53,248 cached, 73.08% cached.

## Why Same Harness Does Not Mean Same Caching

The harness invokes Wattle in the same way, but Wattle does not use the same
provider transport for each backend.

| Path | Transport | Conversation handling |
|---|---|---|
| Wattle / DeepSeek | OpenAI-compatible Chat Completions | Plain message history plus `reasoning_content` replay |
| Wattle / Kimi | OpenAI-compatible Chat Completions | Plain message history plus `reasoning_content` replay |
| Wattle / OpenAI Codex | ChatGPT Codex Responses endpoint | Stateless full transcript, `store=false` |
| Codex agent / OpenAI Codex | Codex CLI/runtime | Different internal protocol and cumulative usage event |

DeepSeek and Kimi report strong cache hits after the first turn. The repeated
prefix in their Chat Completions message history appears to be cacheable.

Wattle/OpenAI Codex sends a different request shape:

- `store` is hard-coded to `false`
- the full transcript is resent every turn
- messages are serialized as Responses-style top-level items
- reasoning blocks and encrypted reasoning content are replayed as items
- function calls and function outputs are replayed as items

This prompt shape seems to produce inconsistent cache hits on the Codex
backend.

## Checked: Not Just a Parser Bug

Wattle/OpenAI Codex reads cached tokens from the raw Codex response field:

```json
"usage": {
  "input_tokens": 12208,
  "input_tokens_details": {
    "cached_tokens": 1536
  }
}
```

That matches the field Wattle parses:

```python
usage["input_tokens_details"]["cached_tokens"]
```

So the low cached-token count is not obviously caused by parsing the wrong
field.

## Checked: Cannot Use Normal Responses Stateful Chaining

The regular OpenAI Responses provider in Wattle is stateful:

- first call: `store=True`
- later calls: `previous_response_id=<id>`
- send only delta messages

The ChatGPT Codex backend used by `openai_codex` rejects that mode. A raw probe
with `store=True` returned:

```text
HTTP 400: Store must be set to false
```

So Wattle cannot simply switch the Codex endpoint to the same
`previous_response_id` flow used by `openai_responses`.

## Additional Probe

A raw Codex endpoint probe with a large stable instruction prefix showed that
cache hits can be inconsistent even for repeated stateless requests.

One three-call probe:

| Call | Input | Cached | Cached / Input |
|---:|---:|---:|---:|
| 1 | 6,018 | 0 | 0.0% |
| 2 | 6,018 | 0 | 0.0% |
| 3 | 6,022 | 5,888 | 97.8% |

A later six-call probe with similar stable-prefix requests reported zero cached
tokens for every call.

This suggests the Codex endpoint's prompt caching for stateless requests may be
opportunistic or sensitive to request shape, timing, routing, prefix threshold,
or fields outside the visible prompt text.

## Current Conclusion

The 22.29% Wattle/OpenAI Codex cache ratio is real for this run. It is not
explained by the Terminal-Bench harness, and it is not obviously explained by
the analyzer parsing the wrong field.

The most likely cause is Wattle's current stateless OpenAI Codex transport and
request shape. The standalone Codex agent likely benefits from a different
internal session/transport protocol, which is why its cumulative usage showed
95.69% cached input.

## Follow-Up Questions

1. Compare Wattle/OpenAI Codex request bodies against Codex CLI's request shape.
2. Determine whether Codex CLI uses a non-public session token, conversation id,
   or protocol that improves cache locality without `store=true`.
3. Test whether removing/reordering replayed reasoning items improves cache hit
   rates without breaking tool-call correctness.
4. Test whether disabling `include=["reasoning.encrypted_content"]` affects
   cache behavior.
5. Test whether putting more stable content in `instructions` and less in
   replayed `input` improves cache behavior.
6. Collect repeated Wattle/OpenAI Codex runs to separate backend variance from
   deterministic request-shape issues.

