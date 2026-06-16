#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


INTERESTING_OUTPUT = re.compile(
    r"(assert |AssertionError|FAILED|ERROR|Traceback|timeout|killed|exit 137|"
    r"reward|accuracy|score|verifier|test_|/app/|model\.bin|result)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CacheSnapshot:
    requests: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    context_tokens: int

    @property
    def cache_rate(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return self.cached_tokens / self.input_tokens


@dataclass(frozen=True)
class TrialSnapshot:
    task: str
    trial: str
    path: Path
    status: str
    reward: Any
    exception_type: str | None
    verifier_failures: list[str]
    last_assistant: str | None
    last_tool: str | None
    cache: CacheSnapshot


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def trial_dirs(run_dir: Path) -> list[Path]:
    jobs = run_dir / "jobs"
    if not jobs.exists():
        return []
    out: list[Path] = []
    for config in jobs.glob("*/*/*/config.json"):
        trial = config.parent
        if (trial / "trial.log").exists() or (trial / "result.json").exists():
            out.append(trial)
    return sorted(out)


def summarize_session(trial: Path) -> tuple[str | None, str | None]:
    sessions = sorted((trial / "agent" / "wattle-sessions").glob("*.jsonl"))
    last_assistant: str | None = None
    last_tool: str | None = None
    for session in sessions:
        try:
            lines = session.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if item.get("type") != "message":
                continue
            message = item.get("message") or {}
            content = message.get("content") or []
            if message.get("role") == "assistant":
                text_parts: list[str] = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text_parts.append(str(block.get("text") or ""))
                    elif block.get("type") == "tool_use":
                        name = block.get("name")
                        raw_input = block.get("input")
                        last_tool = f"{name}: {_compact(raw_input)}"
                text = "\n".join(part for part in text_parts if part.strip()).strip()
                if text:
                    last_assistant = _compact(text, 600)
            elif message.get("role") == "user":
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    text = str(block.get("content") or "")
                    if INTERESTING_OUTPUT.search(text):
                        last_tool = f"tool_result: {_compact(_interesting_lines(text), 800)}"
    return last_assistant, last_tool


def summarize_cache(trial: Path) -> CacheSnapshot:
    sessions = sorted((trial / "agent" / "wattle-sessions").glob("*.jsonl"))
    requests = 0
    input_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    context_tokens = 0
    for session in sessions:
        try:
            lines = session.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if item.get("type") == "message":
                message = item.get("message") or {}
                if message.get("role") != "assistant":
                    continue
                requests += 1
                input_tokens += _int_or_zero(message.get("input_tokens"))
                cached_tokens += _int_or_zero(message.get("cached_tokens"))
                output_tokens += _int_or_zero(message.get("output_tokens"))
            elif item.get("type") == "event":
                event = item.get("event") or {}
                if event.get("type") != "provider_request_prepared":
                    continue
                data = event.get("data") or {}
                context_tokens += _int_or_zero(data.get("context_tokens"))
    return CacheSnapshot(
        requests=requests,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        context_tokens=context_tokens,
    )


def verifier_failures(trial: Path) -> list[str]:
    ctrf = read_json(trial / "verifier" / "ctrf.json")
    failures: list[str] = []
    if not isinstance(ctrf, dict):
        return failures
    tests = ((ctrf.get("results") or {}).get("tests") or [])
    for test in tests:
        if not isinstance(test, dict) or test.get("status") == "passed":
            continue
        name = str(test.get("name") or "unknown-test")
        trace = str(test.get("trace") or "")
        lines = [
            line.strip()
            for line in trace.splitlines()
            if "assert" in line or "Error" in line or "Traceback" in line
        ]
        detail = "; ".join(lines[-3:]) if lines else str(test.get("message") or "")
        failures.append(_compact(f"{name}: {detail}", 600))
    return failures


def snapshot_trial(trial: Path) -> TrialSnapshot:
    result = read_json(trial / "result.json")
    exception_type = None
    reward = None
    status = "running"
    if isinstance(result, dict):
        exception = result.get("exception_info")
        if isinstance(exception, dict):
            exception_type = exception.get("exception_type")
        verifier = result.get("verifier_result")
        if isinstance(verifier, dict):
            rewards = verifier.get("rewards")
            if isinstance(rewards, dict):
                reward = rewards.get("reward")
        if result.get("finished_at"):
            status = "completed"
        if exception_type:
            status = "exception"
        elif reward == 0 or reward == 0.0:
            status = "failed"
        elif reward == 1 or reward == 1.0:
            status = "passed"
    else:
        log = _read_tail(trial / "trial.log")
        if "failed:" in log or "Traceback" in log:
            status = "maybe_failed"

    last_assistant, last_tool = summarize_session(trial)
    return TrialSnapshot(
        task=trial.name.split("__", 1)[0],
        trial=trial.name,
        path=trial,
        status=status,
        reward=reward,
        exception_type=exception_type,
        verifier_failures=verifier_failures(trial),
        last_assistant=last_assistant,
        last_tool=last_tool,
        cache=summarize_cache(trial),
    )


def write_outputs(run_dir: Path, snapshots: list[TrialSnapshot]) -> None:
    out_dir = run_dir / "analysis" / "incremental"
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = now()
    records = [
        {
            "task": snap.task,
            "trial": snap.trial,
            "path": str(snap.path),
            "status": snap.status,
            "reward": snap.reward,
            "exception_type": snap.exception_type,
            "verifier_failures": snap.verifier_failures,
            "last_assistant": snap.last_assistant,
            "last_tool": snap.last_tool,
            "cache": {
                "requests": snap.cache.requests,
                "input_tokens": snap.cache.input_tokens,
                "cached_tokens": snap.cache.cached_tokens,
                "output_tokens": snap.cache.output_tokens,
                "context_tokens": snap.cache.context_tokens,
                "cache_rate": snap.cache.cache_rate,
            },
        }
        for snap in snapshots
    ]
    (out_dir / "snapshot.json").write_text(
        json.dumps({"generated_at": generated, "trials": records}, indent=2) + "\n",
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    for snap in snapshots:
        counts[snap.status] = counts.get(snap.status, 0) + 1

    lines = [
        "# Incremental Wattle Failure Analysis",
        "",
        f"Generated: `{generated}`",
        "",
        "## Counts",
        "",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- `{status}`: {count}")

    total_cache = _sum_cache(snapshots)
    lines.extend(
        [
            "",
            "## Prompt Cache",
            "",
            f"- requests: `{total_cache.requests}`",
            f"- input tokens: `{total_cache.input_tokens}`",
            f"- cached input tokens: `{total_cache.cached_tokens}`",
            f"- cache hit rate: `{total_cache.cache_rate:.1%}`",
            f"- output tokens: `{total_cache.output_tokens}`",
            f"- prepared context tokens: `{total_cache.context_tokens}`",
            "",
            "### By Trial",
            "",
            "| trial | status | requests | input | cached | hit rate | output |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for snap in sorted(snapshots, key=lambda item: item.cache.input_tokens, reverse=True)[:40]:
        lines.append(
            "| "
            f"`{snap.trial}` | `{snap.status}` | {snap.cache.requests} | "
            f"{snap.cache.input_tokens} | {snap.cache.cached_tokens} | "
            f"{snap.cache.cache_rate:.1%} | {snap.cache.output_tokens} |"
        )

    lines.extend(["", "## Notable Trials", ""])

    notable = [
        snap
        for snap in snapshots
        if snap.status not in {"running", "passed"} or snap.verifier_failures
    ]
    for snap in notable[:80]:
        lines.append(f"### `{snap.trial}`")
        lines.append("")
        lines.append(f"- status: `{snap.status}`")
        if snap.reward is not None:
            lines.append(f"- reward: `{snap.reward}`")
        if snap.exception_type:
            lines.append(f"- exception: `{snap.exception_type}`")
        for failure in snap.verifier_failures:
            lines.append(f"- verifier: {failure}")
        if snap.last_tool:
            lines.append(f"- last tool: {snap.last_tool}")
        if snap.last_assistant:
            lines.append(f"- last assistant: {snap.last_assistant}")
        lines.append("")

    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _read_tail(path: Path, max_chars: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def _interesting_lines(text: str) -> str:
    lines = [line for line in text.splitlines() if INTERESTING_OUTPUT.search(line)]
    if not lines:
        return text
    return "\n".join(lines[-12:])


def _compact(value: Any, limit: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 12].rstrip() + " ...[trunc]"


def _int_or_zero(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _sum_cache(snapshots: list[TrialSnapshot]) -> CacheSnapshot:
    return CacheSnapshot(
        requests=sum(snap.cache.requests for snap in snapshots),
        input_tokens=sum(snap.cache.input_tokens for snap in snapshots),
        cached_tokens=sum(snap.cache.cached_tokens for snap in snapshots),
        output_tokens=sum(snap.cache.output_tokens for snap in snapshots),
        context_tokens=sum(snap.cache.context_tokens for snap in snapshots),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    snapshots = [snapshot_trial(path) for path in trial_dirs(run_dir)]
    write_outputs(run_dir, snapshots)
    print(f"{now()} wrote incremental analysis for {len(snapshots)} trials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
