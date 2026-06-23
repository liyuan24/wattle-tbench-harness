#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FORBIDDEN_AGENT_LOG_PATTERNS = (
    "terminal-bench.org",
    "www.terminal-bench.org",
    "terminal-bench.com",
    "www.terminal-bench.com",
    "github.com/laude-institute/terminal-bench",
    "github.com/terminal-bench",
)


@dataclass(frozen=True)
class Finding:
    severity: str
    path: Path
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a Harbor Terminal-Bench run against the machine-checkable "
            "official submission rules."
        )
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Run directory, jobs directory, or a single Harbor job directory.",
    )
    parser.add_argument(
        "--min-trials",
        type=int,
        default=5,
        help="Minimum completed result.json trials required per task.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.path.expanduser().resolve()
    if not root.exists():
        print(f"[error] Path does not exist: {root}", file=sys.stderr)
        return 2

    job_dirs = find_job_dirs(root)
    findings: list[Finding] = []
    if not job_dirs:
        findings.append(Finding("error", root, "No Harbor job directories found."))

    for job_dir in job_dirs:
        findings.extend(validate_job_dir(job_dir, min_trials=args.min_trials))

    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]

    for finding in findings:
        print(f"[{finding.severity}] {finding.path}: {finding.message}")

    if errors:
        print(
            f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s).",
            file=sys.stderr,
        )
        return 1

    print(f"Validation passed: {len(job_dirs)} job(s), {len(warnings)} warning(s).")
    return 0


def find_job_dirs(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for config_path in root.rglob("config.json"):
        directory = config_path.parent
        result_path = directory / "result.json"
        if not result_path.exists():
            continue
        result = read_json(result_path)
        config = read_json(config_path)
        if not isinstance(result, dict) or not isinstance(config, dict):
            continue
        if "task_name" in result:
            continue
        if "job_name" in config or "n_total_trials" in result:
            candidates.append(directory)
    if is_job_dir(root):
        candidates.append(root)
    return sorted(set(candidates))


def is_job_dir(path: Path) -> bool:
    config = read_json(path / "config.json")
    result = read_json(path / "result.json")
    return (
        isinstance(config, dict)
        and isinstance(result, dict)
        and "task_name" not in result
        and ("job_name" in config or "n_total_trials" in result)
    )


def validate_job_dir(job_dir: Path, *, min_trials: int) -> list[Finding]:
    findings: list[Finding] = []
    config_path = job_dir / "config.json"
    config = read_json(config_path)
    if not isinstance(config, dict):
        return [Finding("error", config_path, "Job config.json is missing or invalid JSON.")]

    findings.extend(validate_config(config, config_path))

    trial_dirs = find_trial_dirs(job_dir)
    if not trial_dirs:
        findings.append(Finding("error", job_dir, "No trial directories with result.json found."))
        return findings

    trials_by_task: dict[str, list[Path]] = defaultdict(list)
    for trial_dir in trial_dirs:
        result_path = trial_dir / "result.json"
        result = read_json(result_path)
        if not isinstance(result, dict):
            findings.append(Finding("error", result_path, "Trial result.json is invalid JSON."))
            continue
        task_name = result.get("task_name")
        if not isinstance(task_name, str) or not task_name:
            findings.append(Finding("error", result_path, "Trial result.json lacks task_name."))
            continue
        trials_by_task[task_name].append(trial_dir)
        findings.extend(validate_trial_dir(trial_dir, result))

    for task_name, task_trial_dirs in sorted(trials_by_task.items()):
        if len(task_trial_dirs) < min_trials:
            findings.append(
                Finding(
                    "error",
                    job_dir,
                    f"Task {task_name!r} has {len(task_trial_dirs)} trial(s); "
                    f"minimum is {min_trials}.",
                )
            )

    job_attempts = config.get("n_attempts")
    if isinstance(job_attempts, int) and job_attempts < min_trials:
        findings.append(
            Finding(
                "error",
                config_path,
                f"n_attempts is {job_attempts}; official runs need at least {min_trials}.",
            )
        )

    findings.extend(scan_agent_logs(job_dir))
    return findings


def find_trial_dirs(job_dir: Path) -> list[Path]:
    trial_dirs: list[Path] = []
    for result_path in job_dir.rglob("result.json"):
        if result_path.parent == job_dir:
            continue
        data = read_json(result_path)
        if isinstance(data, dict) and "task_name" in data:
            trial_dirs.append(result_path.parent)
    return sorted(set(trial_dirs))


def validate_trial_dir(trial_dir: Path, result: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    required_fields = ("trial_name", "task_name", "config")
    for field in required_fields:
        if field not in result:
            findings.append(Finding("error", trial_dir / "result.json", f"Missing {field!r}."))

    other_artifacts = [
        path
        for path in trial_dir.iterdir()
        if path.name != "result.json" and not path.name.startswith(".")
    ]
    if not other_artifacts:
        findings.append(
            Finding("error", trial_dir, "Trial directory contains no artifacts beyond result.json.")
        )

    config = result.get("config")
    if isinstance(config, dict):
        findings.extend(validate_config(config, trial_dir / "result.json"))
    else:
        findings.append(Finding("error", trial_dir / "result.json", "Missing embedded config."))
    return findings


def validate_config(config: dict[str, Any], path: Path) -> list[Finding]:
    findings: list[Finding] = []
    timeout_multiplier = config.get("timeout_multiplier")
    if timeout_multiplier != 1.0:
        findings.append(
            Finding(
                "error",
                path,
                f"timeout_multiplier must equal 1.0, got {timeout_multiplier!r}.",
            )
        )

    for key in (
        "agent_timeout_multiplier",
        "verifier_timeout_multiplier",
        "agent_setup_timeout_multiplier",
        "environment_build_timeout_multiplier",
    ):
        if config.get(key) is not None:
            findings.append(Finding("error", path, f"{key} must be null."))

    verifier = config.get("verifier")
    if isinstance(verifier, dict):
        for key in ("override_timeout_sec", "max_timeout_sec"):
            if verifier.get(key) is not None:
                findings.append(Finding("error", path, f"verifier.{key} must be null."))

    environment = config.get("environment")
    if isinstance(environment, dict):
        for key in ("override_cpus", "override_memory_mb", "override_storage_mb"):
            if environment.get(key) is not None:
                findings.append(Finding("error", path, f"environment.{key} must be null."))

    for index, agent in enumerate(as_list(config.get("agents") or config.get("agent"))):
        if not isinstance(agent, dict):
            continue
        for key in ("override_timeout_sec", "max_timeout_sec"):
            if agent.get(key) is not None:
                findings.append(Finding("error", path, f"agent[{index}].{key} must be null."))
    return findings


def scan_agent_logs(job_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    for agent_path in sorted(job_dir.rglob("agent/*")):
        if not agent_path.is_file():
            continue
        try:
            text = agent_path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError as exc:
            findings.append(Finding("warning", agent_path, f"Could not read agent artifact: {exc}"))
            continue
        for pattern in FORBIDDEN_AGENT_LOG_PATTERNS:
            if pattern in text:
                findings.append(
                    Finding(
                        "error",
                        agent_path,
                        "Agent artifact mentions Terminal-Bench website/GitHub repository: "
                        f"{pattern}",
                    )
                )
                break
    return findings


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
