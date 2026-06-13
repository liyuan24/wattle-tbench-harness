#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from model_config import parse_provider_model
from run_tbench import (
    DEFAULT_CODEX_AUTH_PATH,
    DEFAULT_CODEX_CONFIG_PATH,
    DEFAULT_HARBOR_BIN,
    DEFAULT_SOURCE_DIR,
    DEFAULT_WATTLE_AUTH_PATHS,
    first_existing,
    slug,
)

HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_TASK_CACHE_DIR = HARNESS_DIR / "runs/tui-tasks"


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
    )
    parser.add_argument("--codex-auth-path", type=Path, default=DEFAULT_CODEX_AUTH_PATH)
    parser.add_argument("--codex-config-path", type=Path, default=DEFAULT_CODEX_CONFIG_PATH)
    parser.add_argument("--harbor-bin", type=Path, default=Path(DEFAULT_HARBOR_BIN))
    parser.add_argument("--task-cache-dir", type=Path, default=DEFAULT_TASK_CACHE_DIR)
    parser.add_argument("--wattle-provider-request-timeout-sec", type=float, default=120.0)
    parser.add_argument("--wattle-stream-idle-timeout-sec", type=float, default=None)
    parser.add_argument("--session-name", default=None)
    parser.add_argument("--attach", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    return parser.parse_args()


def resolve_task_path(args: argparse.Namespace) -> Path:
    if args.task_path is not None:
        return args.task_path.expanduser().resolve()

    task_dir = args.task_cache_dir.expanduser().resolve() / args.task_name
    if task_dir.exists() or args.no_download:
        return task_dir

    args.task_cache_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(args.harbor_bin),
            "task",
            "download",
            f"terminal-bench/{args.task_name}",
            "--output-dir",
            str(args.task_cache_dir),
        ],
        cwd=HARNESS_DIR,
        check=True,
    )
    return task_dir


def build_start_env_command(args: argparse.Namespace, task_path: Path) -> list[str]:
    return [
        str(args.harbor_bin),
        "task",
        "start-env",
        "--path",
        str(task_path),
        "--interactive",
        "--agent-import-path",
        "wattle_harbor_agent:WattleAgent",
        "-m",
        parse_provider_model(args.model, provider=args.provider).raw,
        "--ak",
        f"source_dir={args.source_dir}",
        "--ak",
        f"wattle_auth_path={args.wattle_auth_path}",
        "--ak",
        f"codex_auth_path={args.codex_auth_path}",
        "--ak",
        f"codex_config_path={args.codex_config_path}",
        "--ak",
        f"thinking={str(args.effort != 'none').lower()}",
        "--ak",
        f"effort={args.effort}",
        "--ak",
        "provider_request_timeout_seconds="
        f"{args.wattle_provider_request_timeout_sec}",
        "--ak",
        "stream_idle_timeout_seconds="
        f"{args.wattle_stream_idle_timeout_sec or args.wattle_provider_request_timeout_sec}",
    ]


def build_wattle_tui_command(args: argparse.Namespace) -> str:
    parsed = parse_provider_model(args.model, provider=args.provider)
    stream_idle_timeout = args.wattle_stream_idle_timeout_sec or (
        args.wattle_provider_request_timeout_sec
    )
    parts = [
        "cd /app",
        "export PATH=\"$HOME/.local/bin:$PATH\"",
        "mkdir -p /logs/agent/wattle-tui-sessions",
        "export WATTLE_SESSION_DIR=/logs/agent/wattle-tui-sessions",
        "export WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS="
        + shlex.quote(str(args.wattle_provider_request_timeout_sec)),
        "export WATTLE_STREAM_IDLE_TIMEOUT_SECONDS=" + shlex.quote(str(stream_idle_timeout)),
        (
            "task_prompt=\"$(cat /task/instruction.md 2>/dev/null || "
            "sed -n '/^instruction:/,$p' /task/task.yaml)\""
        ),
    ]
    command = [
        "wattle",
        "--provider",
        parsed.provider,
        "--model",
        parsed.model,
        "--yolo",
    ]
    if args.effort != "none":
        command.extend(["--thinking", "--effort", args.effort])
    command.append("$task_prompt")
    parts.append(" ".join(shlex.quote(part) for part in command[:-1]) + ' "$task_prompt"')
    return "; ".join(parts)


def launch_tmux(args: argparse.Namespace, start_env_command: list[str], wattle_command: str) -> int:
    if shutil.which("tmux") is None:
        print("[error] tmux is required for the TUI launcher.", file=sys.stderr)
        return 2

    label = args.session_name or (
        "wattle-tbench-tui-"
        + slug(f"{args.task_name}-{parse_provider_model(args.model, provider=args.provider).raw}")
        + "-"
        + datetime.now().strftime("%H%M%S")
    )
    label = label[:100]
    env_prefix = f"export PYTHONPATH={shlex.quote(str(HARNESS_DIR))}:${{PYTHONPATH:-}}; "
    shell_command = env_prefix + " ".join(shlex.quote(part) for part in start_env_command)

    subprocess.run(
        ["tmux", "new-session", "-d", "-s", label, "-c", str(HARNESS_DIR), shell_command],
        check=True,
    )
    time.sleep(2.0)
    subprocess.run(["tmux", "send-keys", "-t", label, wattle_command, "C-m"], check=True)

    print(f"Started tmux session: {label}")
    print(f"Attach with: tmux attach -t {shlex.quote(label)}")
    print("The Wattle TUI command has been queued in the Harbor task shell.")
    if args.attach:
        return subprocess.call(["tmux", "attach", "-t", label])
    return 0


def main() -> int:
    args = parse_args()
    args.source_dir = args.source_dir.expanduser().resolve()
    args.wattle_auth_path = args.wattle_auth_path.expanduser().resolve()
    args.codex_auth_path = args.codex_auth_path.expanduser().resolve()
    args.codex_config_path = args.codex_config_path.expanduser().resolve()
    args.harbor_bin = args.harbor_bin.expanduser().resolve()
    args.task_cache_dir = args.task_cache_dir.expanduser().resolve()

    task_path = resolve_task_path(args)
    if not task_path.exists():
        print(f"[error] Task path does not exist: {task_path}", file=sys.stderr)
        return 2

    start_env_command = build_start_env_command(args, task_path)
    wattle_command = build_wattle_tui_command(args)
    if args.dry_run:
        print("Harbor start-env command:")
        print(" ".join(shlex.quote(part) for part in start_env_command))
        print("\nQueued container command:")
        print(wattle_command)
        return 0

    return launch_tmux(args, start_env_command, wattle_command)


if __name__ == "__main__":
    raise SystemExit(main())
