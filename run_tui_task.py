#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from model_config import parse_provider_model
from run_tbench import (
    DEFAULT_HARBOR_BIN,
    DEFAULT_SOURCE_DIR,
    DEFAULT_WATTLE_AUTH_PATHS,
    first_existing,
)

HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_TASK_CACHE_DIR = HARNESS_DIR / "runs/tui-tasks"
DEFAULT_HARBOR_PACKAGE_CACHE_DIR = Path.home() / ".cache/harbor/tasks/packages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start one Terminal-Bench task in Wattle's interactive TUI."
    )
    parser.add_argument("--task-name", required=True, help="Terminal-Bench task name.")
    parser.add_argument("--task-path", type=Path, default=None, help="Use an existing local task.")
    parser.add_argument("--model", default="deepseek/deepseek-v4-pro", help="provider/model")
    parser.add_argument("--provider", default=None, help="Provider alias for bare --model values.")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--wattle-auth-path",
        type=Path,
        default=first_existing(DEFAULT_WATTLE_AUTH_PATHS),
        help="Deprecated compatibility option; local TUI runs use Wattle's local auth.",
    )
    parser.add_argument(
        "--codex-auth-path",
        type=Path,
        default=None,
        help="Deprecated compatibility option; local TUI runs use Wattle's local auth.",
    )
    parser.add_argument(
        "--codex-config-path",
        type=Path,
        default=None,
        help="Deprecated compatibility option; local TUI runs use Wattle's local config.",
    )
    parser.add_argument("--harbor-bin", type=Path, default=Path(DEFAULT_HARBOR_BIN))
    parser.add_argument("--task-cache-dir", type=Path, default=DEFAULT_TASK_CACHE_DIR)
    parser.add_argument(
        "--harbor-package-cache-dir",
        type=Path,
        default=DEFAULT_HARBOR_PACKAGE_CACHE_DIR,
        help="Harbor package cache used as a fallback when registry download fails.",
    )
    parser.add_argument(
        "--download-attempts",
        type=int,
        default=3,
        help="Number of Harbor task download attempts before failing.",
    )
    parser.add_argument(
        "--download-retry-delay-sec",
        type=float,
        default=5.0,
        help="Seconds to wait between Harbor task download attempts.",
    )
    parser.add_argument("--wattle-provider-request-timeout-sec", type=float, default=None)
    parser.add_argument("--wattle-stream-idle-timeout-sec", type=float, default=None)
    parser.add_argument(
        "--session-name",
        default=None,
        help="Deprecated compatibility option; TUI runs are foreground sessions.",
    )
    parser.add_argument(
        "--attach",
        action="store_true",
        help="Deprecated compatibility option; TUI runs are always attached.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    return parser.parse_args()


def cached_harbor_package_task(args: argparse.Namespace) -> Path | None:
    package_dir = (
        args.harbor_package_cache_dir.expanduser().resolve()
        / "terminal-bench"
        / args.task_name
    )
    if not package_dir.exists():
        return None

    candidates = [
        path
        for path in package_dir.iterdir()
        if path.is_dir() and (path / "task.toml").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def resolve_task_path(args: argparse.Namespace) -> Path:
    if args.task_path is not None:
        return args.task_path.expanduser().resolve()

    task_dir = args.task_cache_dir.expanduser().resolve() / args.task_name
    if task_dir.exists() or args.no_download:
        return task_dir

    args.task_cache_dir.mkdir(parents=True, exist_ok=True)
    download_command = [
        str(args.harbor_bin),
        "task",
        "download",
        f"terminal-bench/{args.task_name}",
        "--output-dir",
        str(args.task_cache_dir),
    ]
    attempts = max(1, args.download_attempts)
    download_error = None
    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                download_command,
                cwd=HARNESS_DIR,
                check=True,
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                text=True,
            )
            if result.stdout:
                print(result.stdout, end="")
            download_error = None
            break
        except subprocess.CalledProcessError as error:
            download_error = error
            if attempt == attempts:
                break
            print(
                "[warn] Harbor task download failed "
                f"(attempt {attempt}/{attempts}); retrying in "
                f"{args.download_retry_delay_sec:g}s...",
                file=sys.stderr,
            )
            time.sleep(max(0.0, args.download_retry_delay_sec))

    if download_error is not None and not task_dir.exists():
        cached_task = cached_harbor_package_task(args)
        if cached_task is not None:
            print(
                "[warn] Harbor task download failed; using cached package task at "
                f"{cached_task}",
                file=sys.stderr,
            )
            shutil.copytree(cached_task, task_dir)
        else:
            if download_error.stdout:
                print(download_error.stdout, end="", file=sys.stderr)
            raise download_error
    return task_dir


def read_task_prompt(task_path: Path) -> str:
    instruction_path = task_path / "instruction.md"
    if instruction_path.exists():
        return instruction_path.read_text(encoding="utf-8").strip()

    task_yaml_path = task_path / "task.yaml"
    if task_yaml_path.exists():
        prompt = _read_instruction_from_task_yaml(task_yaml_path)
        if prompt:
            return prompt

    raise FileNotFoundError(
        f"Task prompt not found at {instruction_path} or {task_yaml_path}"
    )


def _read_instruction_from_task_yaml(task_yaml_path: Path) -> str:
    lines = task_yaml_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("instruction:"):
            continue

        _, value = line.split(":", 1)
        value = value.strip()
        if value and value not in {"|", ">"}:
            return value.strip("'\"")

        block_indent = None
        block_lines: list[str] = []
        for block_line in lines[index + 1 :]:
            if not block_line.strip():
                block_lines.append("")
                continue
            indent = len(block_line) - len(block_line.lstrip(" "))
            if block_indent is None:
                block_indent = indent
            if indent < block_indent:
                break
            block_lines.append(block_line[block_indent:])
        return "\n".join(block_lines).strip()
    return ""


def build_wattle_tui_command(args: argparse.Namespace, task_prompt: str) -> list[str]:
    parsed = parse_provider_model(args.model, provider=args.provider)
    command = build_wattle_executable(args) + [
        "--provider",
        parsed.provider,
        "--model",
        parsed.model,
        "--yolo",
    ]
    if args.effort != "none":
        command.extend(["--thinking", "--effort", args.effort])
    command.append(task_prompt)
    return command


def build_wattle_executable(args: argparse.Namespace) -> list[str]:
    if (args.source_dir / "pyproject.toml").exists():
        return ["uv", "run", "--project", str(args.source_dir), "wattle"]
    return ["wattle"]


def build_wattle_environment(
    args: argparse.Namespace,
    task_path: Path | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env["WATTLE_SESSION_DIR"] = str((HARNESS_DIR / "runs/tui-sessions").resolve())
    if task_path is not None:
        deadline_epoch_ms = _run_deadline_epoch_ms_for_task(task_path)
        if deadline_epoch_ms is not None:
            env["WATTLE_RUN_DEADLINE_EPOCH_MS"] = str(deadline_epoch_ms)
    if args.wattle_provider_request_timeout_sec is not None:
        env["WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS"] = str(
            args.wattle_provider_request_timeout_sec
        )
    if args.wattle_stream_idle_timeout_sec is not None:
        env["WATTLE_STREAM_IDLE_TIMEOUT_SECONDS"] = str(
            args.wattle_stream_idle_timeout_sec
        )
    return env


def launch_wattle_tui(
    args: argparse.Namespace,
    *,
    task_path: Path,
    wattle_command: list[str],
) -> int:
    (HARNESS_DIR / "runs/tui-sessions").mkdir(parents=True, exist_ok=True)
    return subprocess.call(
        wattle_command,
        cwd=task_path,
        env=build_wattle_environment(args, task_path),
    )


def _run_deadline_epoch_ms_for_task(task_path: Path) -> int | None:
    task_toml = task_path / "task.toml"
    if not task_toml.exists():
        return None
    try:
        data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
        timeout = (data.get("agent") or {}).get("timeout_sec")
        if timeout is None:
            return None
        return int((time.time() + float(timeout)) * 1000)
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError):
        return None


def main() -> int:
    args = parse_args()
    args.source_dir = args.source_dir.expanduser().resolve()
    args.wattle_auth_path = args.wattle_auth_path.expanduser().resolve()
    if args.codex_auth_path is not None:
        args.codex_auth_path = args.codex_auth_path.expanduser().resolve()
    if args.codex_config_path is not None:
        args.codex_config_path = args.codex_config_path.expanduser().resolve()
    args.harbor_bin = args.harbor_bin.expanduser().resolve()
    args.task_cache_dir = args.task_cache_dir.expanduser().resolve()

    task_path = resolve_task_path(args)
    if not task_path.exists():
        print(f"[error] Task path does not exist: {task_path}", file=sys.stderr)
        return 2

    task_prompt = read_task_prompt(task_path)
    wattle_command = build_wattle_tui_command(args, task_prompt)
    if args.dry_run:
        print(f"Task path: {task_path}")
        print(f"Working directory: {task_path}")
        print("Wattle TUI command:")
        print(shlex.join(wattle_command))
        return 0

    return launch_wattle_tui(args, task_path=task_path, wattle_command=wattle_command)


if __name__ == "__main__":
    raise SystemExit(main())
