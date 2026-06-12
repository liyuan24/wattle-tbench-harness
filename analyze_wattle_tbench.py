#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "billable_input_tokens",
    "raw_total_tokens",
    "billable_total_tokens",
    "reasoning_output_tokens",
    "codex_footer_billable_total_tokens",
    "final_turn_input_tokens",
    "max_turn_input_tokens",
)


@dataclass
class TaskMetrics:
    run_id: str
    task_id: str
    trial_name: str
    is_resolved: bool
    failure_mode: str
    exception_type: str | None
    exception_message: str | None
    agent_duration_seconds: float | None
    trial_duration_seconds: float | None
    test_duration_seconds: float | None
    session_path: str | None
    session_found: bool
    session_has_usage: bool
    assistant_turns: int
    token_source: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    billable_input_tokens: int
    raw_total_tokens: int
    billable_total_tokens: int
    reasoning_output_tokens: int
    codex_footer_billable_total_tokens: int
    final_turn_input_tokens: int
    max_turn_input_tokens: int


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_seconds(start: object, end: object) -> float | None:
    parsed_start = parse_time(start)
    parsed_end = parse_time(end)
    if parsed_start is None or parsed_end is None:
        return None
    return (parsed_end - parsed_start).total_seconds()


def trial_dir_for(run_dir: Path, result: dict[str, Any]) -> Path:
    return run_dir / str(result["task_id"]) / str(result["trial_name"])


def find_session_file(trial_dir: Path) -> Path | None:
    session_dir = trial_dir / "agent-logs" / "wattle-sessions"
    files = sorted(session_dir.glob("*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def find_embedded_wattle_session(trial_dir: Path) -> tuple[list[str], Path] | None:
    for path in trial_text_log_candidates(trial_dir):
        if not path.exists():
            continue
        lines: list[str] = []
        in_session = False
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("__WATTLE_SESSION_JSONL_BEGIN__"):
                lines = []
                in_session = True
                continue
            if line.startswith("__WATTLE_SESSION_JSONL_END__") and in_session:
                return lines, path
            if in_session:
                lines.append(line)
    return None


def session_token_metrics(path: Path | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "session_path": str(path) if path is not None else None,
        "session_found": path is not None,
        "session_has_usage": False,
        "assistant_turns": 0,
        "token_source": "wattle_session" if path is not None else "none",
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "billable_input_tokens": 0,
        "raw_total_tokens": 0,
        "billable_total_tokens": 0,
        "reasoning_output_tokens": 0,
        "codex_footer_billable_total_tokens": 0,
        "final_turn_input_tokens": 0,
        "max_turn_input_tokens": 0,
    }
    if path is None or not path.exists():
        return metrics

    return session_token_metrics_from_lines(
        path.read_text(encoding="utf-8", errors="replace").splitlines(),
        metrics,
    )


def embedded_wattle_token_metrics(trial_dir: Path) -> dict[str, Any]:
    embedded = find_embedded_wattle_session(trial_dir)
    metrics = session_token_metrics(None)
    if embedded is None:
        return metrics
    lines, path = embedded
    metrics.update(
        {
            "session_path": str(path),
            "session_found": True,
            "token_source": "wattle_embedded_session",
        }
    )
    return session_token_metrics_from_lines(lines, metrics)


def session_token_metrics_from_lines(
    lines: list[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    assistant_inputs: list[int] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        message = item.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        metrics["assistant_turns"] += 1
        input_tokens = int_value(message.get("input_tokens"))
        output_tokens = int_value(message.get("output_tokens"))
        cached_tokens = int_value(message.get("cached_tokens"))
        reasoning_output_tokens = int_value(message.get("reasoning_output_tokens"))
        if input_tokens or output_tokens or cached_tokens:
            metrics["session_has_usage"] = True
        metrics["input_tokens"] += input_tokens
        metrics["output_tokens"] += output_tokens
        metrics["cached_tokens"] += cached_tokens
        metrics["reasoning_output_tokens"] += reasoning_output_tokens
        assistant_inputs.append(input_tokens)

    metrics["billable_input_tokens"] = max(
        0,
        metrics["input_tokens"] - metrics["cached_tokens"],
    )
    metrics["raw_total_tokens"] = metrics["input_tokens"] + metrics["output_tokens"]
    metrics["billable_total_tokens"] = (
        metrics["billable_input_tokens"] + metrics["output_tokens"]
    )
    if assistant_inputs:
        metrics["final_turn_input_tokens"] = assistant_inputs[-1]
        metrics["max_turn_input_tokens"] = max(assistant_inputs)
    return metrics


def codex_token_metrics(trial_dir: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "session_path": None,
        "session_found": False,
        "session_has_usage": False,
        "assistant_turns": 0,
        "token_source": "none",
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "billable_input_tokens": 0,
        "raw_total_tokens": 0,
        "billable_total_tokens": 0,
        "reasoning_output_tokens": 0,
        "codex_footer_billable_total_tokens": 0,
        "final_turn_input_tokens": 0,
        "max_turn_input_tokens": 0,
    }

    events_path = find_codex_events_log(trial_dir)
    if events_path is not None:
        turn_inputs: list[int] = []
        latest_usage: dict[str, object] | None = None
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = _codex_usage_from_event(item)
            if usage is None:
                continue
            latest_usage = usage
            metrics["assistant_turns"] += 1
            turn_inputs.append(int_value(usage.get("input_tokens")))

        if latest_usage is not None:
            metrics["input_tokens"] = int_value(latest_usage.get("input_tokens"))
            metrics["output_tokens"] = int_value(latest_usage.get("output_tokens"))
            metrics["cached_tokens"] = int_value(
                latest_usage.get("cached_input_tokens", latest_usage.get("cached_tokens"))
            )
            metrics["reasoning_output_tokens"] = int_value(
                latest_usage.get("reasoning_output_tokens")
            )
            metrics["session_path"] = str(events_path)
            metrics["session_found"] = True
            metrics["session_has_usage"] = True
            metrics["token_source"] = "codex_json_events"
            metrics["billable_input_tokens"] = max(
                0,
                metrics["input_tokens"] - metrics["cached_tokens"],
            )
            metrics["raw_total_tokens"] = (
                metrics["input_tokens"] + metrics["output_tokens"]
            )
            metrics["billable_total_tokens"] = (
                metrics["billable_input_tokens"] + metrics["output_tokens"]
            )
            metrics["final_turn_input_tokens"] = turn_inputs[-1] if turn_inputs else 0
            metrics["max_turn_input_tokens"] = max(turn_inputs) if turn_inputs else 0
            return metrics

    footer_value, footer_path = find_codex_footer_tokens(trial_dir)
    if footer_value is not None:
        metrics["session_path"] = str(footer_path)
        metrics["session_found"] = True
        metrics["session_has_usage"] = True
        metrics["token_source"] = "codex_footer"
        metrics["billable_total_tokens"] = footer_value
        metrics["codex_footer_billable_total_tokens"] = footer_value
    return metrics


def find_codex_events_log(trial_dir: Path) -> Path | None:
    for path in [
        trial_dir / "agent-logs" / "codex-events.jsonl",
        *trial_text_log_candidates(trial_dir),
    ]:
        if path.exists() and parse_latest_codex_usage(path) is not None:
            return path
    return None


def parse_latest_codex_usage(path: Path) -> dict[str, object] | None:
    latest_usage: dict[str, object] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = _codex_usage_from_event(item)
        if usage is not None:
            latest_usage = usage
    return latest_usage


def _codex_usage_from_event(item: object) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    usage = item.get("usage")
    if isinstance(usage, dict):
        return usage
    msg = item.get("msg")
    if isinstance(msg, dict):
        usage = msg.get("usage")
        if isinstance(usage, dict):
            return usage
    data = item.get("data")
    if isinstance(data, dict):
        usage = data.get("usage")
        if isinstance(usage, dict):
            return usage
    return None


def find_codex_footer_tokens(trial_dir: Path) -> tuple[int | None, Path | None]:
    candidates = [
        trial_dir / "agent-logs" / "codex-output.log",
        trial_dir / "agent-logs" / "codex-stderr.log",
        *trial_text_log_candidates(trial_dir),
    ]
    for path in candidates:
        if not path.exists():
            continue
        value = parse_codex_footer_tokens(path.read_text(encoding="utf-8", errors="replace"))
        if value is not None:
            return value, path
    return None, None


def parse_codex_footer_tokens(text: str) -> int | None:
    match = re.search(r"tokens used\s*\n\s*([0-9][0-9,]*)", text, re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


def trial_text_log_candidates(trial_dir: Path) -> list[Path]:
    return [
        trial_dir / "sessions" / "agent.log",
        trial_dir / "panes" / "post-agent.txt",
    ]


def agent_exception_log_candidates(trial_dir: Path) -> list[Path]:
    return [
        trial_dir / "agent-logs" / "wattle-output.log",
        trial_dir / "agent-logs" / "codex-output.log",
        trial_dir / "sessions" / "agent.log",
        trial_dir / "panes" / "post-agent.txt",
    ]


def trial_exception(trial_dir: Path) -> tuple[str | None, str | None]:
    for path in agent_exception_log_candidates(trial_dir):
        exception = exception_from_text_file(path)
        if exception != (None, None):
            return exception
    return None, None


def exception_from_text_file(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, None
    return exception_from_text(path.read_text(encoding="utf-8", errors="replace"))


def exception_from_text(text: str) -> tuple[str | None, str | None]:
    matches = list(
        re.finditer(
            r"(?P<type>(?:[A-Za-z_][\w]*\.)*[A-Za-z_][\w]*(?:Error|Exception))"
            r":\s*(?P<message>[^\n\r]+)",
            strip_ansi(text),
        )
    )
    if not matches:
        return None, None
    match = matches[-1]
    return match.group("type").rsplit(".", 1)[-1], match.group("message").strip()


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def analyze_run(run_dir: Path) -> list[TaskMetrics]:
    results_path = run_dir / "results.json"
    data = load_json(results_path)
    rows: list[TaskMetrics] = []
    for result in data.get("results", []):
        if not isinstance(result, dict):
            continue
        trial_dir = trial_dir_for(run_dir, result)
        session_path = find_session_file(trial_dir)
        tokens = session_token_metrics(session_path)
        if not tokens["session_found"]:
            tokens = embedded_wattle_token_metrics(trial_dir)
        if not tokens["session_found"]:
            tokens = codex_token_metrics(trial_dir)
        exception_type, exception_message = trial_exception(trial_dir)
        rows.append(
            TaskMetrics(
                run_id=run_dir.name,
                task_id=str(result["task_id"]),
                trial_name=str(result["trial_name"]),
                is_resolved=bool(result.get("is_resolved")),
                failure_mode=str(result.get("failure_mode") or "unset"),
                exception_type=exception_type,
                exception_message=exception_message,
                agent_duration_seconds=duration_seconds(
                    result.get("agent_started_at"),
                    result.get("agent_ended_at"),
                ),
                trial_duration_seconds=duration_seconds(
                    result.get("trial_started_at"),
                    result.get("trial_ended_at"),
                ),
                test_duration_seconds=duration_seconds(
                    result.get("test_started_at"),
                    result.get("test_ended_at"),
                ),
                session_path=tokens["session_path"],
                session_found=bool(tokens["session_found"]),
                session_has_usage=bool(tokens["session_has_usage"]),
                assistant_turns=int(tokens["assistant_turns"]),
                token_source=str(tokens["token_source"]),
                input_tokens=int(tokens["input_tokens"]),
                output_tokens=int(tokens["output_tokens"]),
                cached_tokens=int(tokens["cached_tokens"]),
                billable_input_tokens=int(tokens["billable_input_tokens"]),
                raw_total_tokens=int(tokens["raw_total_tokens"]),
                billable_total_tokens=int(tokens["billable_total_tokens"]),
                reasoning_output_tokens=int(tokens["reasoning_output_tokens"]),
                codex_footer_billable_total_tokens=int(
                    tokens["codex_footer_billable_total_tokens"]
                ),
                final_turn_input_tokens=int(tokens["final_turn_input_tokens"]),
                max_turn_input_tokens=int(tokens["max_turn_input_tokens"]),
            )
        )
    return rows


def stats(values: list[float]) -> dict[str, float | None]:
    clean = [value for value in values if value is not None]
    if not clean:
        return {"avg": None, "median": None, "min": None, "max": None}
    return {
        "avg": statistics.fmean(clean),
        "median": statistics.median(clean),
        "min": min(clean),
        "max": max(clean),
    }


def summarize(rows: list[TaskMetrics]) -> dict[str, Any]:
    by_run: dict[str, list[TaskMetrics]] = {}
    for row in rows:
        by_run.setdefault(row.run_id, []).append(row)

    runs: dict[str, Any] = {}
    for run_id, run_rows in sorted(by_run.items()):
        resolved = sum(1 for row in run_rows if row.is_resolved)
        count = len(run_rows)
        runs[run_id] = {
            "tasks": count,
            "resolved": resolved,
            "unresolved": count - resolved,
            "pass_rate": (resolved / count) if count else None,
            "sessions_found": sum(1 for row in run_rows if row.session_found),
            "sessions_with_usage": sum(1 for row in run_rows if row.session_has_usage),
            "exceptions": {
                exception_type: sum(
                    1 for row in run_rows if row.exception_type == exception_type
                )
                for exception_type in sorted(
                    {row.exception_type for row in run_rows if row.exception_type}
                )
            },
            "token_sources": {
                source: sum(1 for row in run_rows if row.token_source == source)
                for source in sorted({row.token_source for row in run_rows})
            },
            "agent_duration_seconds": stats(
                [row.agent_duration_seconds for row in run_rows if row.agent_duration_seconds is not None]
            ),
            **{
                field: stats([float(getattr(row, field)) for row in run_rows])
                for field in TOKEN_FIELDS
            },
        }
    return {"runs": runs}


def discover_run_dirs(paths: list[Path]) -> list[Path]:
    run_dirs: list[Path] = []
    for path in paths:
        path = path.expanduser().resolve()
        if (path / "results.json").exists():
            run_dirs.append(path)
            continue
        tb_runs = path / "tb-runs"
        if tb_runs.exists():
            run_dirs.extend(sorted(child for child in tb_runs.iterdir() if (child / "results.json").exists()))
            continue
        run_dirs.extend(sorted(child for child in path.iterdir() if child.is_dir() and (child / "results.json").exists()))
    return run_dirs


def write_outputs(rows: list[TaskMetrics], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "tasks.json").write_text(
        json.dumps([asdict(row) for row in rows], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with (output_dir / "tasks.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(asdict(row) for row in rows)

    lines = ["# Terminal-Bench Analysis", ""]
    for run_id, item in summary["runs"].items():
        pass_rate = item["pass_rate"]
        rate_text = "n/a" if pass_rate is None else f"{pass_rate:.2%}"
        lines.extend(
            [
                f"## {run_id}",
                "",
                f"- Pass rate: {item['resolved']} / {item['tasks']} ({rate_text})",
                f"- Sessions found: {item['sessions_found']} / {item['tasks']}",
                f"- Sessions with usage: {item['sessions_with_usage']} / {item['tasks']}",
                f"- Exceptions: {json.dumps(item['exceptions'], sort_keys=True)}",
                f"- Token sources: {json.dumps(item['token_sources'], sort_keys=True)}",
                f"- Agent seconds avg/median/min/max: {format_stats(item['agent_duration_seconds'])}",
                f"- Raw total tokens avg/median/min/max: {format_stats(item['raw_total_tokens'])}",
                f"- Billable total tokens avg/median/min/max: {format_stats(item['billable_total_tokens'])}",
                f"- Input tokens avg/median/min/max: {format_stats(item['input_tokens'])}",
                f"- Output tokens avg/median/min/max: {format_stats(item['output_tokens'])}",
                f"- Cached tokens avg/median/min/max: {format_stats(item['cached_tokens'])}",
                f"- Reasoning output tokens avg/median/min/max: {format_stats(item['reasoning_output_tokens'])}",
                f"- Final-turn input avg/median/min/max: {format_stats(item['final_turn_input_tokens'])}",
                "",
            ]
        )
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def format_stats(item: dict[str, float | None]) -> str:
    values = []
    for key in ("avg", "median", "min", "max"):
        value = item.get(key)
        values.append("n/a" if value is None else f"{value:.2f}")
    return " / ".join(values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Wattle Terminal-Bench runs.")
    parser.add_argument("paths", nargs="+", type=Path, help="Run dir, tb-runs dir, or batch dir.")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dirs = discover_run_dirs(args.paths)
    if not run_dirs:
        raise SystemExit("No Terminal-Bench run directories with results.json found.")
    rows: list[TaskMetrics] = []
    for run_dir in run_dirs:
        rows.extend(analyze_run(run_dir))
    output_dir = args.output_dir or (run_dirs[0].parent / "analysis")
    write_outputs(rows, output_dir)
    print(f"Wrote analysis to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
