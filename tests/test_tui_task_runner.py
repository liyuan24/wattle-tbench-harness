from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from run_tui_task import (
    build_wattle_environment,
    build_wattle_tui_command,
    read_task_prompt,
    resolve_task_path,
)


def _args(**overrides: object) -> argparse.Namespace:
    data = {
        "codex_auth_path": Path("/home/user/.codex/auth.json"),
        "codex_config_path": Path("/home/user/.codex/config.toml"),
        "effort": "high",
        "harbor_bin": Path("/bin/harbor"),
        "harbor_package_cache_dir": Path("/harbor/packages"),
        "model": "deepseek/deepseek-v4-pro",
        "download_attempts": 3,
        "download_retry_delay_sec": 5.0,
        "provider": None,
        "source_dir": Path("/src/wattle"),
        "task_cache_dir": Path("/tasks"),
        "task_name": "break-filter-js-from-html",
        "task_path": None,
        "no_download": False,
        "wattle_auth_path": Path("/home/user/.wattle/auth.json"),
        "wattle_provider_request_timeout_sec": None,
        "wattle_stream_idle_timeout_sec": None,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_wattle_tui_command_uses_positional_prompt_not_headless_print() -> None:
    command = build_wattle_tui_command(_args(), "Do the task.")

    assert command == [
        "wattle",
        "--provider",
        "deepseek",
        "--model",
        "deepseek-v4-pro",
        "--yolo",
        "--thinking",
        "--effort",
        "high",
        "Do the task.",
    ]
    assert "--print" not in command
    assert "-p" not in command


def test_wattle_tui_command_uses_source_checkout_when_available(tmp_path: Path) -> None:
    source_dir = tmp_path / "wattle"
    source_dir.mkdir()
    (source_dir / "pyproject.toml").write_text("[project]\nname = 'wattle'\n", encoding="utf-8")

    command = build_wattle_tui_command(_args(source_dir=source_dir), "Do the task.")

    assert command[:4] == ["uv", "run", "--project", str(source_dir)]
    assert command[4] == "wattle"


def test_read_task_prompt_uses_instruction_md(tmp_path: Path) -> None:
    (tmp_path / "instruction.md").write_text("Do the task.\n", encoding="utf-8")

    assert read_task_prompt(tmp_path) == "Do the task."


def test_read_task_prompt_falls_back_to_task_yaml_block(tmp_path: Path) -> None:
    (tmp_path / "task.yaml").write_text(
        "name: example\ninstruction: |\n  First line.\n  Second line.\n",
        encoding="utf-8",
    )

    assert read_task_prompt(tmp_path) == "First line.\nSecond line."


def test_wattle_environment_sets_timeout_only_when_requested() -> None:
    env = build_wattle_environment(
        _args(
            wattle_provider_request_timeout_sec=120.0,
            wattle_stream_idle_timeout_sec=None,
        )
    )

    assert env["WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS"] == "120.0"
    assert "WATTLE_STREAM_IDLE_TIMEOUT_SECONDS" not in env


def test_wattle_environment_sets_run_deadline_from_task(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    (tmp_path / "task.toml").write_text(
        "[agent]\ntimeout_sec = 900.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("run_tui_task.time.time", lambda: 1000.0)

    env = build_wattle_environment(_args(), tmp_path)

    assert env["WATTLE_RUN_DEADLINE_EPOCH_MS"] == "1900000"


def test_resolve_task_path_uses_existing_cached_task(tmp_path: Path) -> None:
    task_dir = tmp_path / "break-filter-js-from-html"
    task_dir.mkdir()

    resolved = resolve_task_path(_args(task_cache_dir=tmp_path))

    assert resolved == task_dir.resolve()


def test_resolve_task_path_retries_failed_download(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    calls = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append((command, kwargs))
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("run_tui_task.time.sleep", lambda _: None)

    resolved = resolve_task_path(
        _args(
            task_cache_dir=tmp_path,
            harbor_bin=Path("/bin/harbor"),
            download_retry_delay_sec=0.0,
        )
    )

    assert resolved == (tmp_path / "break-filter-js-from-html").resolve()
    assert len(calls) == 2
    assert calls[0][0] == [
        "/bin/harbor",
        "task",
        "download",
        "terminal-bench/break-filter-js-from-html",
        "--output-dir",
        str(tmp_path.resolve()),
    ]


def test_resolve_task_path_falls_back_to_harbor_package_cache(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    package_cache_dir = tmp_path / "package-cache"
    cached_task = (
        package_cache_dir
        / "terminal-bench"
        / "break-filter-js-from-html"
        / "cached-content-hash"
    )
    cached_task.mkdir(parents=True)
    (cached_task / "task.toml").write_text("[task]\n", encoding="utf-8")
    (cached_task / "instruction.md").write_text("Do the task.\n", encoding="utf-8")

    def fake_run(command: list[str], **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, command)

    task_cache_dir = tmp_path / "tasks"
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("run_tui_task.time.sleep", lambda _: None)

    resolved = resolve_task_path(
        _args(
            task_cache_dir=task_cache_dir,
            harbor_package_cache_dir=package_cache_dir,
            download_attempts=1,
        )
    )

    assert resolved == (task_cache_dir / "break-filter-js-from-html").resolve()
    assert (resolved / "task.toml").read_text(encoding="utf-8") == "[task]\n"
    assert (resolved / "instruction.md").read_text(encoding="utf-8") == "Do the task.\n"
