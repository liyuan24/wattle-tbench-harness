#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Harbor Terminal-Bench reports.")
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir
    out_dir = args.out_dir or results_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    trials = list(_iter_trials(results_dir))
    per_task = _build_per_task_rows(trials)
    aggregate = _build_aggregate(trials, per_task)

    _write_csv(out_dir / "per_trial.csv", trials)
    _write_json(out_dir / "per_trial.json", trials)
    _write_csv(out_dir / "per_task.csv", per_task)
    _write_json(out_dir / "per_task.json", per_task)
    _write_json(out_dir / "aggregate.json", aggregate)
    _write_markdown(out_dir / "summary.md", aggregate)

    print(f"Wrote reports to {out_dir}")
    print(f"Trials: {len(trials)}")
    return 0


def _iter_trials(results_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(results_dir.rglob("result.json")):
        data = _read_json(path)
        if not isinstance(data, dict) or "task_name" not in data:
            continue

        agent_info = data.get("agent_info") or {}
        model_info = agent_info.get("model_info") or {}
        agent_result = data.get("agent_result") or {}
        verifier_result = data.get("verifier_result") or {}
        rewards = verifier_result.get("rewards") or {}
        exception_info = data.get("exception_info")
        metadata = agent_result.get("metadata") or {}

        reward = _number_or_none(rewards.get("reward"))
        score_reward = reward if reward is not None else 0.0
        row = {
            "job_name": _job_name_from_trial_path(path),
            "trial_name": data.get("trial_name"),
            "task_name": data.get("task_name"),
            "provider": model_info.get("provider") or metadata.get("provider"),
            "model": model_info.get("name") or metadata.get("model"),
            "raw_model": metadata.get("raw_model"),
            "reward": reward,
            "score_reward": score_reward,
            "resolved": reward == 1.0 if reward is not None else None,
            "exception_type": _exception_field(exception_info, "type", "exception_type"),
            "exception_message": _exception_field(exception_info, "message", "exception_message"),
            "n_input_tokens": int(agent_result.get("n_input_tokens") or 0),
            "n_cache_tokens": int(agent_result.get("n_cache_tokens") or 0),
            "n_output_tokens": int(agent_result.get("n_output_tokens") or 0),
            "started_at": data.get("started_at"),
            "finished_at": data.get("finished_at"),
            "runtime_sec": _runtime_seconds(data.get("started_at"), data.get("finished_at")),
            "trial_uri": data.get("trial_uri"),
            "result_path": str(path),
        }
        rows.append(row)
    return rows


def _build_per_task_rows(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        grouped[(trial["provider"], trial["model"], trial["task_name"])].append(trial)

    rows: list[dict[str, Any]] = []
    for (provider, model, task_name), items in sorted(grouped.items()):
        rows.append(
            {
                "provider": provider,
                "model": model,
                "task_name": task_name,
                "n_trials": len(items),
                "n_errors": sum(1 for item in items if item["exception_type"]),
                "mean_reward": sum(item["score_reward"] for item in items) / len(items)
                if items
                else None,
                "n_input_tokens": sum(item["n_input_tokens"] for item in items),
                "n_cache_tokens": sum(item["n_cache_tokens"] for item in items),
                "n_output_tokens": sum(item["n_output_tokens"] for item in items),
                "runtime_sec": sum(item["runtime_sec"] or 0 for item in items),
            }
        )
    return rows


def _build_aggregate(
    trials: list[dict[str, Any]],
    per_task: list[dict[str, Any]],
) -> dict[str, Any]:
    by_model: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trial in trials:
        by_model[(trial["provider"], trial["model"])].append(trial)

    model_rows = []
    for (provider, model), items in sorted(by_model.items()):
        exceptions = Counter(item["exception_type"] or "none" for item in items)
        model_rows.append(
            {
                "provider": provider,
                "model": model,
                "n_trials": len(items),
                "n_errors": sum(1 for item in items if item["exception_type"]),
                "mean_reward": sum(item["score_reward"] for item in items) / len(items)
                if items
                else None,
                "n_input_tokens": sum(item["n_input_tokens"] for item in items),
                "n_cache_tokens": sum(item["n_cache_tokens"] for item in items),
                "n_output_tokens": sum(item["n_output_tokens"] for item in items),
                "runtime_sec": sum(item["runtime_sec"] or 0 for item in items),
                "exceptions": dict(sorted(exceptions.items())),
            }
        )

    exceptions = Counter(item["exception_type"] or "none" for item in trials)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "n_trials": len(trials),
        "n_errors": sum(1 for item in trials if item["exception_type"]),
        "mean_reward": sum(item["score_reward"] for item in trials) / len(trials)
        if trials
        else None,
        "n_input_tokens": sum(item["n_input_tokens"] for item in trials),
        "n_cache_tokens": sum(item["n_cache_tokens"] for item in trials),
        "n_output_tokens": sum(item["n_output_tokens"] for item in trials),
        "runtime_sec": sum(item["runtime_sec"] or 0 for item in trials),
        "exceptions": dict(sorted(exceptions.items())),
        "by_model": model_rows,
        "per_task_rows": len(per_task),
    }


def _write_markdown(path: Path, aggregate: dict[str, Any]) -> None:
    lines = [
        "# Harbor Terminal-Bench Report",
        "",
        f"Generated: `{aggregate['generated_at']}`",
        "",
        "| Provider | Model | Trials | Mean Reward | Errors | Input Tokens | "
        "Cache Tokens | Output Tokens | Runtime Sec |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate["by_model"]:
        mean = row["mean_reward"]
        mean_text = "" if mean is None else f"{mean:.2%}"
        lines.append(
            f"| `{row['provider']}` | `{row['model']}` | {row['n_trials']} | "
            f"{mean_text} | {row['n_errors']} | {row['n_input_tokens']} | "
            f"{row['n_cache_tokens']} | {row['n_output_tokens']} | "
            f"{row['runtime_sec']:.1f} |"
        )
    lines.extend(["", "Exception summary:", ""])
    for name, count in aggregate["exceptions"].items():
        lines.append(f"- `{name}`: {count}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _job_name_from_trial_path(path: Path) -> str:
    parents = list(path.parents)
    for parent in parents:
        if parent.name.startswith(("codex-", "wattle-")):
            return parent.name
    return parents[2].name if len(parents) > 2 else ""


def _exception_field(exception_info: Any, *fields: str) -> str | None:
    if not isinstance(exception_info, dict):
        return None
    for field in fields:
        value = exception_info.get(field)
        if value:
            return str(value)
    return None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _runtime_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (finished - started).total_seconds()


if __name__ == "__main__":
    raise SystemExit(main())
