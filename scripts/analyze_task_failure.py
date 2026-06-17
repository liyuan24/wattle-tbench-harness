#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


HARNESS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = "terminal-bench@2.0"
DEFAULT_TASK_CACHE_DIR = HARNESS_DIR / "runs/analysis-tasks"
DEFAULT_ANALYSIS_DIRNAME = "failure_analysis"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a reusable failure-analysis evidence report for one task."
    )
    parser.add_argument("task_name")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=HARNESS_DIR / "runs/gcp/wattle-gpt55-tbench20-amd64-gcp-3attempt-20260616",
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--task-cache-dir", type=Path, default=DEFAULT_TASK_CACHE_DIR)
    parser.add_argument(
        "--codex-run-dir",
        type=Path,
        default=None,
        help="Optional synced Codex comparison run directory.",
    )
    parser.add_argument("--download-task", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    analysis_dir = run_dir / "analysis" / DEFAULT_ANALYSIS_DIRNAME
    task_report = analysis_dir / "tasks" / f"{args.task_name}.md"
    ledger_path = analysis_dir / "ledger.jsonl"
    if task_report.exists() and not args.force:
        print(f"Already analyzed: {task_report}")
        return 0

    task_dir = find_or_download_task(args)
    wattle_trials = find_trials(run_dir, args.task_name)
    codex_trials = (
        find_trials(args.codex_run_dir.expanduser().resolve(), args.task_name)
        if args.codex_run_dir is not None
        else []
    )

    report = build_report(
        task_name=args.task_name,
        run_dir=run_dir,
        task_dir=task_dir,
        wattle_trials=wattle_trials,
        codex_trials=codex_trials,
    )
    task_report.parent.mkdir(parents=True, exist_ok=True)
    task_report.write_text(report, encoding="utf-8")

    record = {
        "analyzed_at": now(),
        "task_name": args.task_name,
        "run_dir": str(run_dir),
        "task_report": str(task_report),
        "wattle_trials": [trial.name for trial in wattle_trials],
        "codex_trials": [trial.name for trial in codex_trials],
        "task_dir": str(task_dir) if task_dir else None,
        "report_sha256": sha256_text(report),
    }
    write_ledger_record(ledger_path, record)

    print(f"Wrote analysis report: {task_report}")
    print(f"Updated ledger: {ledger_path}")
    return 0


def write_ledger_record(ledger_path: Path, record: dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    if ledger_path.exists():
        for raw in ledger_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            same_task = item.get("task_name") == record.get("task_name")
            same_run = item.get("run_dir") == record.get("run_dir")
            if same_task and same_run:
                continue
            records.append(item)
    records.append(record)
    ledger_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def find_or_download_task(args: argparse.Namespace) -> Path | None:
    task_name = args.task_name
    candidates = [
        HARNESS_DIR / "runs/tui-tasks/terminal-bench" / task_name,
        args.task_cache_dir.expanduser().resolve() / dataset_export_name(args.dataset) / task_name,
    ]
    candidates.extend(Path.home().glob(f".cache/harbor/tasks/*/{task_name}"))
    for path in candidates:
        if path.exists() and (path / "task.toml").exists():
            return path

    if not args.download_task:
        return None

    harbor = HARNESS_DIR / ".venv/bin/harbor"
    if not harbor.exists():
        harbor = Path("harbor")
    args.task_cache_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(harbor),
        "download",
        args.dataset,
        "--output-dir",
        str(args.task_cache_dir),
        "--overwrite",
    ]
    print("$", " ".join(command), file=sys.stderr)
    subprocess.run(command, cwd=HARNESS_DIR, check=True)
    path = args.task_cache_dir.expanduser().resolve() / dataset_export_name(args.dataset) / task_name
    return path if path.exists() else None


def dataset_export_name(dataset: str) -> str:
    return dataset.rsplit("/", 1)[-1].split("@", 1)[0]


def find_trials(run_dir: Path, task_name: str) -> list[Path]:
    jobs = run_dir / "jobs"
    if not jobs.exists():
        return []
    return sorted(
        path
        for path in jobs.glob(f"*/*/{task_name}__*")
        if path.is_dir() and ((path / "result.json").exists() or (path / "trial.log").exists())
    )


def build_report(
    *,
    task_name: str,
    run_dir: Path,
    task_dir: Path | None,
    wattle_trials: list[Path],
    codex_trials: list[Path],
) -> str:
    lines = [
        f"# Failure Analysis: `{task_name}`",
        "",
        f"Generated: `{now()}`",
        f"Run dir: `{run_dir}`",
        "",
        "## Status",
        "",
    ]
    if not wattle_trials:
        lines.append("- Wattle trials: none found")
    for trial in wattle_trials:
        lines.extend(trial_status_lines("Wattle", trial))

    lines.extend(["", "## Oracle And Tests", ""])
    if task_dir is None:
        lines.append("- Task directory not found. Rerun with `--download-task` enabled.")
    else:
        lines.append(f"- Task dir: `{task_dir}`")
        append_file_excerpt(lines, task_dir / "instruction.md", "Instruction", limit=5000)
        append_file_excerpt(lines, task_dir / "solution/solve.sh", "Oracle Solution", limit=8000)
        append_file_excerpt(lines, task_dir / "tests/test_outputs.py", "Verifier Tests", limit=8000)
        append_file_excerpt(lines, task_dir / "task.toml", "Task Metadata", limit=3000)

    lines.extend(["", "## Wattle Evidence", ""])
    for trial in wattle_trials:
        append_trial_evidence(lines, trial)

    lines.extend(["", "## Codex Comparison Evidence", ""])
    if not codex_trials:
        lines.extend(
            [
                "No Codex comparison trial was provided.",
                "",
                "To collect one on the VM:",
                "",
                "```bash",
                "cd ~/repos/wattle-tbench-harness",
                f"./run_tbench.py --agent codex --model gpt-5.5 --include-task-name {task_name} --n-attempts 1 --n-concurrent 1 --run-label codex-compare-{task_name} --tmux",
                "```",
            ]
        )
    for trial in codex_trials:
        append_trial_evidence(lines, trial)

    lines.extend(
        [
            "",
            "## Analysis Notes",
            "",
            "- Fill in: failure pattern.",
            "- Fill in: grounded oracle/test contrast.",
            "- Fill in: general Wattle improvement hypothesis.",
            "- Fill in: whether Codex comparison is needed or already available.",
            "",
        ]
    )
    return "\n".join(lines)


def trial_status_lines(label: str, trial: Path) -> list[str]:
    result = read_json(trial / "result.json")
    reward = None
    exception_type = None
    if isinstance(result, dict):
        reward = (((result.get("verifier_result") or {}).get("rewards") or {}).get("reward"))
        exc = result.get("exception_info")
        if isinstance(exc, dict):
            exception_type = exc.get("exception_type") or exc.get("type")
    status = "unknown"
    if exception_type:
        status = f"exception:{exception_type}"
    elif reward == 1 or reward == 1.0:
        status = "passed"
    elif reward == 0 or reward == 0.0:
        status = "failed"
    elif not (trial / "result.json").exists():
        status = "running-or-incomplete"
    return [f"- {label} trial `{trial.name}`: `{status}` reward=`{reward}`"]


def append_trial_evidence(lines: list[str], trial: Path) -> None:
    lines.extend(["", f"### `{trial.name}`", ""])
    result = read_json(trial / "result.json")
    if isinstance(result, dict):
        verifier = result.get("verifier_result") or {}
        rewards = verifier.get("rewards") or {}
        exc = result.get("exception_info")
        lines.append(f"- reward: `{rewards.get('reward')}`")
        if exc:
            lines.append(f"- exception: `{compact(exc, 1000)}`")
    failures = verifier_failures(trial)
    if failures:
        lines.extend(["", "Verifier failures:", ""])
        for failure in failures:
            lines.append(f"- {failure}")

    append_file_excerpt(lines, trial / "agent/wattle-output.log", "Agent Output Log", limit=5000)
    append_session_summary(lines, trial)
    append_file_excerpt(lines, trial / "trial.log", "Trial Log Tail", limit=5000, tail=True)
    append_file_excerpt(lines, trial / "verifier/test-stdout.txt", "Verifier Stdout", limit=5000)


def append_session_summary(lines: list[str], trial: Path) -> None:
    sessions = sorted((trial / "agent" / "wattle-sessions").glob("*.jsonl"))
    if not sessions:
        return
    lines.extend(["", "Session summary:", ""])
    for session in sessions:
        lines.append(f"- session: `{session.name}`")
        for item in session_events(session)[-16:]:
            lines.append(f"  - {item}")


def session_events(path: Path) -> list[str]:
    events: list[str] = []
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for raw in raw_lines:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if item.get("type") == "message":
            message = item.get("message") or {}
            role = message.get("role")
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = compact(block.get("text") or "", 600)
                    if text:
                        events.append(f"{role}: {text}")
                elif block.get("type") == "tool_use":
                    events.append(f"tool_use:{block.get('name')}: {compact(block.get('input'), 500)}")
                elif block.get("type") == "tool_result":
                    events.append(f"tool_result: {compact(block.get('content'), 600)}")
        elif item.get("type") == "event":
            event = item.get("event") or {}
            if event.get("type") in {"provider_request_prepared", "provider_response_completed"}:
                events.append(f"event:{event.get('type')}: {compact(event.get('data'), 400)}")
    return events


def verifier_failures(trial: Path) -> list[str]:
    ctrf = read_json(trial / "verifier/ctrf.json")
    if not isinstance(ctrf, dict):
        return []
    failures: list[str] = []
    for test in ((ctrf.get("results") or {}).get("tests") or []):
        if not isinstance(test, dict) or test.get("status") == "passed":
            continue
        name = str(test.get("name") or "unknown-test")
        trace = str(test.get("trace") or test.get("message") or "")
        failures.append(compact(f"{name}: {trace}", 1200))
    return failures


def append_file_excerpt(
    lines: list[str],
    path: Path,
    title: str,
    *,
    limit: int,
    tail: bool = False,
) -> None:
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        lines.extend(["", f"### {title}", "", f"Could not read `{path}`: `{exc}`"])
        return
    excerpt = text[-limit:] if tail and len(text) > limit else text[:limit]
    trunc = "\n\n...[truncated]...\n" if len(text) > limit else ""
    lines.extend(
        [
            "",
            f"### {title}",
            "",
            f"Path: `{path}`",
            "",
            "```text",
            excerpt.rstrip() + trunc,
            "```",
        ]
    )


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def compact(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, default=str)
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 12].rstrip() + " ...[trunc]"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
