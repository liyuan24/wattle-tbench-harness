#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from model_config import parse_codex_model, parse_provider_model
from run_tbench import (
    AGENTS,
    DEFAULT_CODEX_AUTH_PATH,
    DEFAULT_CODEX_CONFIG_PATH,
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
        description="Start one Terminal-Bench task container in an interactive agent TUI."
    )
    parser.add_argument("--agent", choices=sorted(AGENTS), default="wattle")
    parser.add_argument("--task-name", required=True, help="Terminal-Bench task name.")
    parser.add_argument("--task-path", type=Path, default=None, help="Use an existing local task.")
    parser.add_argument("--model", default=None, help="Model name. Defaults by --agent.")
    parser.add_argument(
        "--provider",
        default=None,
        help="Wattle provider alias for bare --model values.",
    )
    parser.add_argument("--effort", default="high")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--wattle-auth-path",
        type=Path,
        default=first_existing(DEFAULT_WATTLE_AUTH_PATHS),
        help="Wattle auth file to mount into the task container.",
    )
    parser.add_argument(
        "--codex-auth-path",
        type=Path,
        default=DEFAULT_CODEX_AUTH_PATH,
        help="Codex auth file to copy into the task container for --agent codex.",
    )
    parser.add_argument(
        "--codex-config-path",
        type=Path,
        default=DEFAULT_CODEX_CONFIG_PATH,
        help="Codex config file to copy into the task container for --agent codex.",
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
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run Wattle on the host in the task directory instead of a task container.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Do not build environment/Dockerfile; pull/use the task.toml docker_image instead.",
    )
    parser.add_argument(
        "--remove-container",
        action="store_true",
        help="Remove the task container when the TUI exits.",
    )
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
    parsed = parse_provider_model(args.model or "deepseek/deepseek-v4-pro", provider=args.provider)
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


def slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return (clean or "task").lower()


def read_task_docker_image(task_path: Path) -> str | None:
    task_toml = task_path / "task.toml"
    if not task_toml.exists():
        return None
    data = tomllib.loads(task_toml.read_text(encoding="utf-8"))
    image = (data.get("environment") or {}).get("docker_image")
    return image if isinstance(image, str) and image else None


def local_task_image_tag(args: argparse.Namespace) -> str:
    return f"{args.agent}-tui-{slug(args.task_name)}:latest"


def build_task_image_command(args: argparse.Namespace, task_path: Path) -> list[str] | None:
    dockerfile = task_path / "environment" / "Dockerfile"
    if args.no_build or not dockerfile.exists():
        return None
    return [
        "docker",
        "build",
        "-t",
        local_task_image_tag(args),
        str(dockerfile.parent),
    ]


def pull_task_image_command(task_path: Path) -> list[str] | None:
    image = read_task_docker_image(task_path)
    if image is None:
        return None
    return ["docker", "pull", image]


def task_container_image(args: argparse.Namespace, task_path: Path) -> str:
    if not args.no_build and (task_path / "environment" / "Dockerfile").exists():
        return local_task_image_tag(args)
    image = read_task_docker_image(task_path)
    if image is None:
        raise FileNotFoundError(
            f"No Dockerfile at {task_path / 'environment' / 'Dockerfile'} "
            f"and no environment.docker_image in {task_path / 'task.toml'}"
        )
    return image


def build_container_wattle_command(args: argparse.Namespace, task_prompt: str) -> str:
    parsed = parse_provider_model(args.model or "deepseek/deepseek-v4-pro", provider=args.provider)
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
    command.append(task_prompt)
    return shlex.join(command)


def container_bootstrap_command(args: argparse.Namespace, task_prompt: str) -> str:
    wattle_command = build_container_wattle_command(args, task_prompt)
    return "\n".join(
        [
            "set -euo pipefail",
            "export DEBIAN_FRONTEND=noninteractive",
            "apt-get update",
            "apt-get install -y --no-install-recommends "
            "ca-certificates curl git python3 python3-venv tar gzip",
            "apt-get clean",
            "rm -rf /var/lib/apt/lists/*",
            "if ! command -v uv >/dev/null 2>&1; then "
            "curl -LsSf https://astral.sh/uv/install.sh | sh; fi",
            'export PATH="$HOME/.local/bin:$PATH"',
            "mkdir -p /root/.wattle /logs/agent/wattle-sessions",
            "cp /tmp/wattle-auth.json /root/.wattle/auth.json",
            "chmod 700 /root/.wattle",
            "chmod 600 /root/.wattle/auth.json",
            "uv --no-cache tool install --force -e /wattle-src",
            "rm -rf /tmp/uv-cache",
            "cd /app",
            wattle_command,
        ]
    )


def build_container_codex_command(args: argparse.Namespace, task_prompt: str) -> str:
    parsed = parse_codex_model(args.model)
    command = [
        "codex",
        "-m",
        parsed.model,
        "--dangerously-bypass-approvals-and-sandbox",
        "-C",
        "/app",
        task_prompt,
    ]
    return shlex.join(command)


def codex_container_bootstrap_command(args: argparse.Namespace, task_prompt: str) -> str:
    codex_command = build_container_codex_command(args, task_prompt)
    return "\n".join(
        [
            "set -euo pipefail",
            "export DEBIAN_FRONTEND=noninteractive",
            "apt-get update",
            "apt-get install -y --no-install-recommends ca-certificates curl git gnupg",
            "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
            "apt-get install -y --no-install-recommends nodejs",
            "npm install -g @openai/codex",
            "apt-get clean",
            "rm -rf /var/lib/apt/lists/*",
            "mkdir -p /root/.codex",
            "cp /tmp/codex-auth.json /root/.codex/auth.json",
            "chmod 700 /root/.codex",
            "chmod 600 /root/.codex/auth.json",
            "if [ -f /tmp/codex-config.toml ]; then "
            "cp /tmp/codex-config.toml /root/.codex/config.toml; "
            "chmod 600 /root/.codex/config.toml; fi",
            "cd /app",
            "if [ ! -d .git ]; then git init >/dev/null 2>&1 || true; fi",
            codex_command,
        ]
    )


def build_docker_run_command(
    args: argparse.Namespace,
    *,
    task_path: Path,
    task_prompt: str,
    container_name: str,
) -> list[str]:
    args.source_dir = args.source_dir.expanduser().resolve()
    session_dir = (HARNESS_DIR / "runs/tui-sessions").resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    command = ["docker", "run"]
    if args.remove_container:
        command.append("--rm")
    command.extend(["-it", "--name", container_name])
    if args.agent == "codex":
        args.codex_auth_path = args.codex_auth_path.expanduser().resolve()
        command.extend(["-v", f"{args.codex_auth_path}:/tmp/codex-auth.json:ro"])
        if args.codex_config_path is not None and args.codex_config_path.exists():
            args.codex_config_path = args.codex_config_path.expanduser().resolve()
            command.extend(["-v", f"{args.codex_config_path}:/tmp/codex-config.toml:ro"])
    else:
        args.wattle_auth_path = args.wattle_auth_path.expanduser().resolve()
        command.extend(
            [
                "-v",
                f"{args.source_dir}:/wattle-src:ro",
                "-v",
                f"{args.wattle_auth_path}:/tmp/wattle-auth.json:ro",
                "-v",
                f"{session_dir}:/logs/agent/wattle-sessions",
                "-e",
                "WATTLE_SESSION_DIR=/logs/agent/wattle-sessions",
            ]
        )
    deadline_epoch_ms = _run_deadline_epoch_ms_for_task(task_path)
    if args.agent == "wattle" and deadline_epoch_ms is not None:
        command.extend(["-e", f"WATTLE_RUN_DEADLINE_EPOCH_MS={deadline_epoch_ms}"])
    if args.agent == "wattle" and args.wattle_provider_request_timeout_sec is not None:
        command.extend(
            [
                "-e",
                "WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS="
                f"{args.wattle_provider_request_timeout_sec}",
            ]
        )
    if args.agent == "wattle" and args.wattle_stream_idle_timeout_sec is not None:
        command.extend(
            [
                "-e",
                "WATTLE_STREAM_IDLE_TIMEOUT_SECONDS="
                f"{args.wattle_stream_idle_timeout_sec}",
            ]
        )
    command.extend([task_container_image(args, task_path), "bash", "-lc"])
    if args.agent == "codex":
        command.append(codex_container_bootstrap_command(args, task_prompt))
    else:
        command.append(container_bootstrap_command(args, task_prompt))
    return command


def prepare_task_container_image(args: argparse.Namespace, task_path: Path) -> None:
    build_command = build_task_image_command(args, task_path)
    if build_command is not None:
        subprocess.run(build_command, cwd=HARNESS_DIR, check=True)
        return
    pull_command = pull_task_image_command(task_path)
    if pull_command is not None:
        subprocess.run(pull_command, cwd=HARNESS_DIR, check=True)


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


def launch_container_wattle_tui(
    args: argparse.Namespace,
    *,
    task_path: Path,
    task_prompt: str,
    container_name: str,
) -> int:
    prepare_task_container_image(args, task_path)
    docker_command = build_docker_run_command(
        args,
        task_path=task_path,
        task_prompt=task_prompt,
        container_name=container_name,
    )
    print(f"Container name: {container_name}")
    if args.remove_container:
        print("Container will be removed when the TUI exits.")
    else:
        print(f"Copy task output after exit with: docker cp {container_name}:/app ./app-output")
        print(f"Remove container with: docker rm {container_name}")
    return subprocess.call(docker_command, cwd=HARNESS_DIR)


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
    args.wattle_auth_path = args.wattle_auth_path.expanduser().resolve()

    task_path = resolve_task_path(args)
    if not task_path.exists():
        print(f"[error] Task path does not exist: {task_path}", file=sys.stderr)
        return 2
    if args.agent == "codex" and args.local:
        print("[error] --agent codex requires the task container; omit --local.", file=sys.stderr)
        return 2
    if args.agent == "codex" and not args.codex_auth_path.exists():
        print(f"[error] Codex auth file does not exist: {args.codex_auth_path}", file=sys.stderr)
        return 2
    if args.agent == "wattle" and not args.local and not args.wattle_auth_path.exists():
        print(f"[error] Wattle auth file does not exist: {args.wattle_auth_path}", file=sys.stderr)
        return 2

    task_prompt = read_task_prompt(task_path)
    container_name = slug(
        args.session_name or f"{args.agent}-tui-{args.task_name}-{int(time.time())}"
    )
    if args.dry_run:
        print(f"Task path: {task_path}")
        if args.local:
            wattle_command = build_wattle_tui_command(args, task_prompt)
            print(f"Working directory: {task_path}")
            print("Wattle TUI command:")
            print(shlex.join(wattle_command))
        else:
            build_command = build_task_image_command(args, task_path)
            pull_command = pull_task_image_command(task_path) if build_command is None else None
            if build_command is not None:
                print("Task image build command:")
                print(shlex.join(build_command))
            elif pull_command is not None:
                print("Task image pull command:")
                print(shlex.join(pull_command))
            print("Container TUI command:")
            print(
                shlex.join(
                    build_docker_run_command(
                        args,
                        task_path=task_path,
                        task_prompt=task_prompt,
                        container_name=container_name,
                    )
                )
            )
        return 0

    if args.local:
        wattle_command = build_wattle_tui_command(args, task_prompt)
        return launch_wattle_tui(args, task_path=task_path, wattle_command=wattle_command)

    return launch_container_wattle_tui(
        args,
        task_path=task_path,
        task_prompt=task_prompt,
        container_name=container_name,
    )


if __name__ == "__main__":
    raise SystemExit(main())
