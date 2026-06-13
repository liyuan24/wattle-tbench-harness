#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from model_config import parse_provider_model

HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = HARNESS_DIR / "runs"
DEFAULT_SOURCE_DIR = Path("/home/liyuan/repos/wattle")
DEFAULT_WATTLE_AUTH_PATHS = [
    Path.home() / ".wattle/auth.json",
    Path.home() / ".willow/auth.json",
]
DEFAULT_CODEX_AUTH_PATH = Path.home() / ".codex/auth.json"
DEFAULT_CODEX_CONFIG_PATH = Path.home() / ".codex/config.toml"
DEFAULT_DATASET = "terminal-bench@2.0"
DEFAULT_HARBOR_BIN = shutil.which("harbor") or "/home/liyuan/.local/bin/harbor"
EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


@dataclass(frozen=True)
class HarborRun:
    name: str
    job_name: str
    model: str
    provider: str
    model_name: str


@dataclass
class RunResult:
    job_name: str
    model: str
    exit_code: int
    command_path: str
    log_path: str
    job_dir: str
    report_dir: str | None


def slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return (clean or "case").lower()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.expanduser().exists():
            return path.expanduser()
    return paths[0].expanduser()


def build_run(args: argparse.Namespace) -> HarborRun:
    parsed = parse_provider_model(args.model, provider=args.provider)
    effort_part = args.effort if args.effort else "none"
    name = slug(f"wattle-{parsed.provider}-{parsed.model}-{effort_part}")
    if args.task:
        name = slug(f"{name}-{args.task}")
    elif args.include_task_name:
        name = slug(f"{name}-subset")
    job_name = slug(args.job_name or name)
    return HarborRun(
        name=name,
        job_name=job_name,
        model=parsed.raw,
        provider=parsed.provider,
        model_name=parsed.model,
    )


def build_tmux_child_args(
    raw_args: list[str],
    *,
    args: argparse.Namespace,
    label: str,
) -> list[str]:
    child_args = [arg for arg in raw_args if arg != "--tmux"]
    has_run_label = "--run-label" in child_args or any(
        arg.startswith("--run-label=") for arg in child_args
    )
    if not has_run_label:
        child_args.extend(["--run-label", label])
    for option, value in (
        ("--output-dir", str(args.output_dir.expanduser().resolve())),
        ("--source-dir", str(args.source_dir.expanduser().resolve())),
        ("--harbor-bin", str(args.harbor_bin)),
        ("--wattle-auth-path", str(args.wattle_auth_path.expanduser().resolve())),
        ("--codex-auth-path", str(args.codex_auth_path.expanduser().resolve())),
        ("--codex-config-path", str(args.codex_config_path.expanduser().resolve())),
    ):
        child_args = strip_option(child_args, option)
        child_args.extend([option, value])
    return child_args


def strip_option(raw_args: list[str], option: str) -> list[str]:
    stripped: list[str] = []
    skip_next = False
    for arg in raw_args:
        if skip_next:
            skip_next = False
            continue
        if arg == option:
            skip_next = True
            continue
        if arg.startswith(f"{option}="):
            continue
        stripped.append(arg)
    return stripped


def launch_tmux_run(*, raw_args: list[str], args: argparse.Namespace, label: str) -> int:
    if shutil.which("tmux") is None:
        print("[error] --tmux requested, but tmux was not found on PATH.", file=sys.stderr)
        return 2

    session_name = f"harbor-tbench-{slug(label)}"[:100]
    output_dir = args.output_dir.expanduser().resolve()
    child_args = build_tmux_child_args(raw_args, args=args, label=label)
    child_command = [sys.executable, str(Path(__file__).resolve()), *child_args]
    shell_command = (
        " ".join(shlex.quote(part) for part in child_command)
        + "; run_tbench_status=$?; "
        + "printf '\\n[run_tbench] exited with status %s\\n' \"$run_tbench_status\"; "
        + "printf '[run_tbench] summary: %s\\n' "
        + shlex.quote(str(output_dir / label / "summary.md"))
    )
    try:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session_name, "-c", str(HARNESS_DIR)],
            check=True,
        )
        subprocess.run(["tmux", "send-keys", "-t", session_name, shell_command, "C-m"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[error] Failed to create tmux session {session_name!r}: {exc}", file=sys.stderr)
        return exc.returncode or 1

    print(f"Started tmux session: {session_name}")
    print(f"Attach with: tmux attach -t {shlex.quote(session_name)}")
    print(f"Output dir: {output_dir / label}")
    return 0


def build_harbor_command(
    *,
    args: argparse.Namespace,
    run: HarborRun,
    job_dir: Path,
) -> list[str]:
    command = [
        str(args.harbor_bin),
        "run",
        "-d",
        args.dataset,
        "--agent-import-path",
        "wattle_harbor_agent:WattleAgent",
        "-m",
        run.model,
        "--job-name",
        run.job_name,
        "--jobs-dir",
        str(job_dir),
        "-n",
        str(args.n_concurrent),
        "--n-attempts",
        str(args.n_attempts),
        "--yes",
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
    ]
    if args.max_tokens is not None:
        command.extend(["--ak", f"max_tokens={args.max_tokens}"])
    if args.wattle_provider_request_timeout_sec is not None:
        command.extend(
            [
                "--ak",
                "provider_request_timeout_seconds="
                f"{args.wattle_provider_request_timeout_sec}",
            ]
        )
    if args.wattle_stream_idle_timeout_sec is not None:
        command.extend(
            [
                "--ak",
                "stream_idle_timeout_seconds="
                f"{args.wattle_stream_idle_timeout_sec}",
            ]
        )
    if args.force_build:
        command.append("--force-build")
    if args.no_delete:
        command.append("--no-delete")
    if args.debug:
        command.append("--debug")
    if args.timeout_multiplier is not None:
        command.extend(["--timeout-multiplier", str(args.timeout_multiplier)])
    if args.agent_timeout_multiplier is not None:
        command.extend(["--agent-timeout-multiplier", str(args.agent_timeout_multiplier)])
    if args.verifier_timeout_multiplier is not None:
        command.extend(["--verifier-timeout-multiplier", str(args.verifier_timeout_multiplier)])
    if args.n_tasks is not None:
        command.extend(["--n-tasks", str(args.n_tasks)])
    for task in args.task:
        command.extend(["-t", task])
    for task in args.include_task_name:
        command.extend(["--include-task-name", task])
    for task in args.exclude_task_name:
        command.extend(["--exclude-task-name", task])
    for item in args.agent_env:
        command.extend(["--agent-env", item])
    for item in args.extra_harbor_arg:
        command.append(item)
    return command


def run_logged(command: list[str], *, cwd: Path, env: dict[str, str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    printable = " ".join(shlex.quote(part) for part in command)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"$ {printable}\n\n")
        handle.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            handle.write(line)
            handle.flush()
        return process.wait()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_inputs(args: argparse.Namespace) -> None:
    if not Path(args.harbor_bin).exists():
        raise FileNotFoundError(f"Harbor binary not found: {args.harbor_bin}")
    if not args.source_dir.exists():
        raise FileNotFoundError(f"Wattle source dir not found: {args.source_dir}")
    if not args.wattle_auth_path.exists() and not args.codex_auth_path.exists():
        env_auth = any(
            os.environ.get(name)
            for name in (
                "ANTHROPIC_API_KEY",
                "CODEX_OAUTH_TOKEN",
                "DEEPSEEK_API_KEY",
                "KIMI_API_KEY",
                "MINIMAX_API_KEY",
                "OPENAI_API_KEY",
            )
        )
        if not env_auth:
            raise FileNotFoundError(
                "No auth source found. Provide --wattle-auth-path, --codex-auth-path, "
                "or provider API key environment variables."
            )


def write_summary(batch_dir: Path, results: list[RunResult]) -> None:
    lines = [
        "# Harbor Terminal-Bench Batch",
        "",
        f"Generated: `{utc_now()}`",
        "",
        "| Job | Model | Exit | Job Dir | Reports | Log |",
        "|---|---|---:|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| `{result.job_name}` | `{result.model}` | {result.exit_code} | "
            f"`{result.job_dir}` | `{result.report_dir or ''}` | `{result.log_path}` |"
        )
    lines.append("")
    (batch_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(batch_dir / "results.json", [asdict(result) for result in results])


def generate_reports(results_root: Path) -> Path | None:
    script = HARNESS_DIR / "scripts/generate_reports.py"
    if not script.exists():
        return None
    proc = subprocess.run([sys.executable, str(script), str(results_root)], cwd=HARNESS_DIR)
    return results_root / "reports" if proc.returncode == 0 else None


def git_commit_and_dirty(repo_dir: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return None, None
    return commit, bool(status.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Wattle against Harbor / Terminal-Bench 2.0."
    )
    parser.add_argument("--provider", default=None, help="Provider alias for bare --model values.")
    parser.add_argument("--model", default="deepseek/deepseek-v4-pro", help="provider/model")
    parser.add_argument("--effort", choices=sorted(EFFORTS), default="high")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--task", action="append", default=[], help="Harbor registry task id.")
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        dest="include_task_name",
        help="Compatibility alias for --include-task-name.",
    )
    parser.add_argument("--include-task-name", action="append", default=[])
    parser.add_argument("--exclude-task-name", action="append", default=[])
    parser.add_argument("--n-tasks", type=int, default=None)
    parser.add_argument("--n-concurrent", type=int, default=2)
    parser.add_argument("--n-attempts", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--wattle-provider-request-timeout-sec", type=float, default=None)
    parser.add_argument("--wattle-stream-idle-timeout-sec", type=float, default=None)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--wattle-auth-path",
        type=Path,
        default=first_existing(DEFAULT_WATTLE_AUTH_PATHS),
    )
    parser.add_argument("--codex-auth-path", type=Path, default=DEFAULT_CODEX_AUTH_PATH)
    parser.add_argument("--codex-config-path", type=Path, default=DEFAULT_CODEX_CONFIG_PATH)
    parser.add_argument("--harbor-bin", type=Path, default=Path(DEFAULT_HARBOR_BIN))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--timeout-multiplier", type=float, default=None)
    parser.add_argument("--agent-timeout-multiplier", type=float, default=None)
    parser.add_argument("--verifier-timeout-multiplier", type=float, default=None)
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--no-delete", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tmux", action="store_true")
    parser.add_argument("--skip-reports", action="store_true")
    parser.add_argument("--agent-env", action="append", default=[])
    parser.add_argument("--extra-harbor-arg", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    raw_args = sys.argv[1:]
    args = parse_args()
    args.source_dir = args.source_dir.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.wattle_auth_path = args.wattle_auth_path.expanduser().resolve()
    args.codex_auth_path = args.codex_auth_path.expanduser().resolve()
    args.codex_config_path = args.codex_config_path.expanduser().resolve()
    args.harbor_bin = args.harbor_bin.expanduser().resolve()
    args.include_task_name = [*args.include_task_name]

    try:
        validate_inputs(args)
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    run = build_run(args)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = slug(args.run_label) if args.run_label else f"{timestamp}-{run.name}"
    batch_dir = args.output_dir / label
    if batch_dir.exists():
        print(f"[error] Output directory already exists: {batch_dir}", file=sys.stderr)
        return 2
    if args.tmux:
        return launch_tmux_run(raw_args=raw_args, args=args, label=label)

    jobs_root = batch_dir / "jobs"
    logs_dir = batch_dir / "logs"
    commands_dir = batch_dir / "commands"
    for path in (jobs_root, logs_dir, commands_dir):
        path.mkdir(parents=True, exist_ok=True)

    wattle_commit, wattle_dirty = git_commit_and_dirty(args.source_dir)
    harness_commit, harness_dirty = git_commit_and_dirty(HARNESS_DIR)

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(HARNESS_DIR)
        if not env.get("PYTHONPATH")
        else f"{HARNESS_DIR}:{env['PYTHONPATH']}"
    )

    write_json(
        batch_dir / "manifest.json",
        {
            "created_at": utc_now(),
            "dataset": args.dataset,
            "harness_commit": harness_commit,
            "harness_dirty": harness_dirty,
            "wattle_commit": wattle_commit,
            "wattle_dirty": wattle_dirty,
            "wattle_source_dir": str(args.source_dir),
            "args": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
        },
    )

    job_dir = jobs_root / run.job_name
    command = build_harbor_command(args=args, run=run, job_dir=job_dir)
    command_path = commands_dir / f"{run.job_name}.json"
    log_path = logs_dir / f"{run.job_name}.log"
    write_json(
        command_path,
        {
            "cwd": str(HARNESS_DIR),
            "env": {"PYTHONPATH": env["PYTHONPATH"]},
            "command": command,
        },
    )

    print(f"\n=== Running {run.job_name}: {run.model} ===")
    print(f"Dataset: {args.dataset}")
    print(f"Wattle commit: {wattle_commit}")
    print(f"Job dir: {job_dir}")
    if args.dry_run:
        print("Dry run; command written to", command_path)
        log_path.write_text("[dry-run] command not executed\n", encoding="utf-8")
        exit_code = 0
        report_dir = None
    else:
        exit_code = run_logged(command, cwd=HARNESS_DIR, env=env, log_path=log_path)
        report_dir = None if args.skip_reports else generate_reports(batch_dir)

    result = RunResult(
        job_name=run.job_name,
        model=run.model,
        exit_code=exit_code,
        command_path=str(command_path),
        log_path=str(log_path),
        job_dir=str(job_dir),
        report_dir=str(report_dir) if report_dir is not None else None,
    )
    write_summary(batch_dir, [result])
    print(f"\nWrote batch summary: {batch_dir / 'summary.md'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
