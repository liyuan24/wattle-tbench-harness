#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from analyze_wattle_tbench import analyze_run, write_outputs


HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = HARNESS_DIR / "runs"
DEFAULT_SOURCE_DIR = Path("/home/liyuan/repos/wattle")
DEFAULT_WATTLE_AUTH_PATH = Path.home() / ".wattle/auth.json"
DEFAULT_CODEX_AUTH_PATH = Path.home() / ".codex/auth.json"
DEFAULT_CODEX_CONFIG_PATH = Path.home() / ".codex/config.toml"
EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
AGENTS = {"wattle", "codex"}


@dataclass(frozen=True)
class EvalCase:
    name: str
    agent: str
    provider: str | None
    model: str
    thinking: bool
    effort: str | None


@dataclass
class RunResult:
    case: str
    run_id: str
    exit_code: int
    command_path: str
    log_path: str
    analysis_dir: str | None


def build_source_archive(source_dir: Path, output_path: Path) -> None:
    excludes = [
        "--exclude=.git",
        "--exclude=.venv",
        "--exclude=__pycache__",
        "--exclude=.pytest_cache",
        "--exclude=.mypy_cache",
        "--exclude=.ruff_cache",
        "--exclude=runs",
    ]
    subprocess.run(
        ["tar", *excludes, "-czf", str(output_path), "-C", str(source_dir), "."],
        check=True,
    )


def build_case(args: argparse.Namespace) -> EvalCase:
    effort = args.effort
    resolved_effort = None if effort == "none" else effort
    if args.agent == "wattle":
        name = slug(f"wattle-{args.provider}-{args.model}-{effort}")
        provider = args.provider
    else:
        name = slug(f"codex-{args.model}-{effort}")
        provider = None
    return EvalCase(
        agent=args.agent,
        name=name,
        provider=provider,
        model=args.model,
        thinking=resolved_effort is not None,
        effort=resolved_effort,
    )


def slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return (clean or "case").lower()


def has_arg(raw_args: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(f"{option}=") for arg in raw_args)


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


def tmux_session_name(label: str) -> str:
    return f"tbench-{slug(label)}"[:100]


def build_tmux_child_args(raw_args: list[str], *, args: argparse.Namespace, label: str) -> list[str]:
    child_args = [arg for arg in raw_args if arg != "--tmux"]
    if not has_arg(child_args, "--run-label"):
        child_args.extend(["--run-label", label])
    for option in (
        "--output-dir",
        "--source-dir",
        "--wattle-auth-path",
        "--codex-auth-path",
        "--codex-config-path",
    ):
        child_args = strip_option(child_args, option)
    child_args.extend(
        [
            "--output-dir",
            str(args.output_dir.expanduser().resolve()),
            "--source-dir",
            str(args.source_dir.expanduser().resolve()),
            "--wattle-auth-path",
            str(args.wattle_auth_path.expanduser().resolve()),
            "--codex-auth-path",
            str(args.codex_auth_path.expanduser().resolve()),
            "--codex-config-path",
            str(args.codex_config_path.expanduser().resolve()),
        ]
    )
    return child_args


def launch_tmux_run(*, raw_args: list[str], args: argparse.Namespace, label: str) -> int:
    if shutil.which("tmux") is None:
        print("[error] --tmux requested, but tmux was not found on PATH.", file=sys.stderr)
        return 2

    session_name = tmux_session_name(label)
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
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-c",
                str(HARNESS_DIR),
            ],
            check=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, shell_command, "C-m"],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[error] Failed to create tmux session {session_name!r}: {exc}", file=sys.stderr)
        return exc.returncode or 1

    print(f"Started tmux session: {session_name}")
    print(f"Attach with: tmux attach -t {shlex.quote(session_name)}")
    print(f"Output dir: {output_dir / label}")
    return 0


def build_tb_command(
    *,
    args: argparse.Namespace,
    case: EvalCase,
    run_id: str,
    tb_output_path: Path,
    source_tgz: Path,
) -> list[str]:
    if case.agent == "codex":
        return build_codex_tb_command(
            args=args,
            case=case,
            run_id=run_id,
            tb_output_path=tb_output_path,
        )
    return build_wattle_tb_command(
        args=args,
        case=case,
        run_id=run_id,
        tb_output_path=tb_output_path,
        source_tgz=source_tgz,
    )


def build_wattle_tb_command(
    *,
    args: argparse.Namespace,
    case: EvalCase,
    run_id: str,
    tb_output_path: Path,
    source_tgz: Path,
) -> list[str]:
    assert case.provider is not None
    command = [
        "tb",
        "run",
        "--dataset",
        args.dataset,
        "--agent-import-path",
        "wattle_tbench_agent:WattleInstalledAgent",
        "--model",
        f"{case.provider}/{case.model}",
        "--n-concurrent",
        str(args.n_concurrent),
        "--n-attempts",
        str(args.n_attempts),
        "--run-id",
        run_id,
        "--output-path",
        str(tb_output_path),
        "--no-upload-results",
        "--log-level",
        args.log_level,
        "--agent-kwarg",
        f"provider={case.provider}",
        "--agent-kwarg",
        f"model={case.model}",
        "--agent-kwarg",
        f"thinking={str(case.thinking).lower()}",
        "--agent-kwarg",
        f"effort={case.effort or 'none'}",
        "--agent-kwarg",
        f"max_tokens={args.max_tokens}",
        "--agent-kwarg",
        f"source_tgz_path={source_tgz}",
        "--agent-kwarg",
        f"wattle_auth_path={args.wattle_auth_path}",
        "--agent-kwarg",
        f"codex_auth_path={args.codex_auth_path}",
        "--agent-kwarg",
        f"codex_config_path={args.codex_config_path}",
    ]
    if args.wattle_provider_request_timeout_sec is not None:
        command.extend(
            [
                "--agent-kwarg",
                "provider_request_timeout_seconds="
                f"{args.wattle_provider_request_timeout_sec}",
            ]
        )
    append_common_tb_args(command, args)
    return command


def build_codex_tb_command(
    *,
    args: argparse.Namespace,
    case: EvalCase,
    run_id: str,
    tb_output_path: Path,
) -> list[str]:
    command = [
        "tb",
        "run",
        "--dataset",
        args.dataset,
        "--agent-import-path",
        "codex_tbench_agent:CodexInstalledAgent",
        "--model",
        f"openai/{case.model}",
        "--n-concurrent",
        str(args.n_concurrent),
        "--n-attempts",
        str(args.n_attempts),
        "--run-id",
        run_id,
        "--output-path",
        str(tb_output_path),
        "--no-upload-results",
        "--log-level",
        args.log_level,
        "--agent-kwarg",
        f"model={case.model}",
        "--agent-kwarg",
        f"effort={case.effort or 'none'}",
        "--agent-kwarg",
        f"auth_path={args.codex_auth_path}",
        "--agent-kwarg",
        f"codex_config_path={args.codex_config_path}",
    ]
    append_common_tb_args(command, args)
    return command


def append_common_tb_args(command: list[str], args: argparse.Namespace) -> None:
    for task_id in args.task_id:
        command.extend(["--task-id", task_id])
    if args.n_tasks is not None:
        command.extend(["--n-tasks", str(args.n_tasks)])
    for task_id in args.exclude_task_id:
        command.extend(["--exclude-task-id", task_id])
    if args.no_rebuild:
        command.append("--no-rebuild")
    if args.no_cleanup:
        command.append("--no-cleanup")
    if args.livestream:
        command.append("--livestream")
    if args.global_timeout_multiplier is not None:
        command.extend(["--global-timeout-multiplier", str(args.global_timeout_multiplier)])
    if args.global_agent_timeout_sec is not None:
        command.extend(["--global-agent-timeout-sec", str(args.global_agent_timeout_sec)])
    if args.global_test_timeout_sec is not None:
        command.extend(["--global-test-timeout-sec", str(args.global_test_timeout_sec)])
    for item in args.extra_tb_arg:
        command.append(item)


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
    if args.agent == "wattle" and not args.source_dir.exists():
        raise FileNotFoundError(f"Wattle source dir not found: {args.source_dir}")
    if args.agent == "wattle" and not args.wattle_auth_path.exists() and not args.codex_auth_path.exists():
        raise FileNotFoundError(
            "No auth file found. Expected at least one of "
            f"{args.wattle_auth_path} or {args.codex_auth_path}."
        )
    if args.agent == "codex" and not args.codex_auth_path.exists():
        raise FileNotFoundError(f"Codex auth file not found: {args.codex_auth_path}")


def write_batch_summary(batch_dir: Path, results: list[RunResult]) -> None:
    lines = [
        "# Terminal-Bench Batch",
        "",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "| Case | Run ID | Exit | Analysis | Log |",
        "|---|---|---:|---|---|",
    ]
    for result in results:
        analysis = result.analysis_dir or ""
        lines.append(
            f"| `{result.case}` | `{result.run_id}` | {result.exit_code} | "
            f"`{analysis}` | `{result.log_path}` |"
        )
    lines.append("")
    (batch_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(batch_dir / "results.json", [asdict(result) for result in results])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Wattle or Codex against Terminal-Bench.")
    parser.add_argument("--agent", choices=sorted(AGENTS), default="wattle")
    parser.add_argument("--provider", default="openai_codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--effort", choices=sorted(EFFORTS), default="none")
    parser.add_argument("--dataset", default="terminal-bench-core==0.1.1")
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--exclude-task-id", action="append", default=[])
    parser.add_argument("--n-tasks", type=int, default=None)
    parser.add_argument("--n-concurrent", type=int, default=4)
    parser.add_argument("--n-attempts", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--wattle-provider-request-timeout-sec", type=float, default=None)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--wattle-auth-path", type=Path, default=DEFAULT_WATTLE_AUTH_PATH)
    parser.add_argument("--codex-auth-path", type=Path, default=DEFAULT_CODEX_AUTH_PATH)
    parser.add_argument("--codex-config-path", type=Path, default=DEFAULT_CODEX_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--livestream", action="store_true")
    parser.add_argument("--no-rebuild", action="store_true")
    parser.add_argument("--no-cleanup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--tmux",
        action="store_true",
        help="Launch this run in a detached tmux session and return immediately.",
    )
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--global-timeout-multiplier", type=float, default=None)
    parser.add_argument("--global-agent-timeout-sec", type=float, default=None)
    parser.add_argument("--global-test-timeout-sec", type=float, default=None)
    parser.add_argument("--extra-tb-arg", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    raw_args = sys.argv[1:]
    args = parse_args()
    try:
        validate_inputs(args)
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    case = build_case(args)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = slug(args.run_label) if args.run_label else f"{timestamp}-{case.name}"
    batch_dir = args.output_dir / label
    if batch_dir.exists():
        print(f"[error] Output directory already exists: {batch_dir}", file=sys.stderr)
        return 2
    if args.tmux:
        return launch_tmux_run(raw_args=raw_args, args=args, label=label)

    tb_output_path = batch_dir / "tb-runs"
    logs_dir = batch_dir / "logs"
    commands_dir = batch_dir / "commands"
    assets_dir = batch_dir / "assets"
    analysis_dir = batch_dir / "analysis"
    for path in (tb_output_path, logs_dir, commands_dir, assets_dir, analysis_dir):
        path.mkdir(parents=True, exist_ok=True)

    source_tgz = assets_dir / "wattle-source.tgz"
    if args.agent == "wattle":
        print(f"Packing Wattle source: {args.source_dir} -> {source_tgz}")
        build_source_archive(args.source_dir, source_tgz)

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(HARNESS_DIR)
        if not env.get("PYTHONPATH")
        else f"{HARNESS_DIR}:{env['PYTHONPATH']}"
    )

    write_json(
        batch_dir / "config.json",
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "batch_dir": str(batch_dir),
            "tb_output_path": str(tb_output_path),
            "case": asdict(case),
            "args": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
        },
    )

    results: list[RunResult] = []
    all_rows = []
    run_id = label
    command = build_tb_command(
        args=args,
        case=case,
        run_id=run_id,
        tb_output_path=tb_output_path,
        source_tgz=source_tgz,
    )
    command_path = commands_dir / f"{case.name}.json"
    log_path = logs_dir / f"{case.name}.log"
    write_json(
        command_path,
        {
            "cwd": str(HARNESS_DIR),
            "env": {"PYTHONPATH": env["PYTHONPATH"]},
            "command": command,
        },
    )
    print(f"\n=== Running {case.name}: {run_id} ===")
    if args.dry_run:
        print("Dry run; command written to", command_path)
        exit_code = 0
        log_path.write_text("[dry-run] command not executed\n", encoding="utf-8")
        case_analysis_dir = None
    else:
        exit_code = run_logged(command, cwd=HARNESS_DIR, env=env, log_path=log_path)
        run_dir = tb_output_path / run_id
        case_analysis_dir = analysis_dir / case.name
        if not args.skip_analysis and (run_dir / "results.json").exists():
            rows = analyze_run(run_dir)
            write_outputs(rows, case_analysis_dir)
            all_rows.extend(rows)
    result = RunResult(
        case=case.name,
        run_id=run_id,
        exit_code=exit_code,
        command_path=str(command_path),
        log_path=str(log_path),
        analysis_dir=str(case_analysis_dir) if case_analysis_dir is not None else None,
    )
    results.append(result)
    write_json(batch_dir / "results.json", [asdict(item) for item in results])

    if all_rows and not args.skip_analysis:
        write_outputs(all_rows, analysis_dir / "combined")
    write_batch_summary(batch_dir, results)
    print(f"\nWrote batch summary: {batch_dir / 'summary.md'}")
    return 0 if all(result.exit_code == 0 for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
