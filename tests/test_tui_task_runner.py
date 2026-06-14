from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from run_tui_task import build_start_env_command, build_wattle_tui_command, resolve_task_path


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


def test_start_env_command_installs_wattle_agent() -> None:
    command = build_start_env_command(_args(), Path("/tasks/break-filter-js-from-html"))

    assert command[:4] == ["/bin/harbor", "task", "start-env", "--path"]
    assert "--interactive" in command
    assert "--agent-import-path" in command
    assert "wattle_harbor_agent:WattleAgent" in command
    assert "-m" in command
    assert "deepseek/deepseek-v4-pro" in command
    assert "source_dir=/src/wattle" in command
    assert "provider_request_timeout_seconds=120.0" not in command
    assert "stream_idle_timeout_seconds=120.0" not in command


def test_start_env_command_can_pass_explicit_provider_timeout() -> None:
    command = build_start_env_command(
        _args(wattle_provider_request_timeout_sec=120.0),
        Path("/tasks/break-filter-js-from-html"),
    )

    assert "provider_request_timeout_seconds=120.0" in command
    assert "stream_idle_timeout_seconds=120.0" not in command


def test_wattle_tui_command_uses_positional_prompt_not_headless_print() -> None:
    command = build_wattle_tui_command(_args())

    assert "cat /task/instruction.md" in command
    assert "wattle --provider deepseek --model deepseek-v4-pro --yolo" in command
    assert "--thinking --effort high" in command
    assert '"$task_prompt"' in command
    wattle_invocation = command.rsplit("; wattle ", 1)[1]
    assert " -p " not in f" {wattle_invocation} "
    assert "--print" not in command


def test_wattle_tui_command_omits_timeout_exports_by_default() -> None:
    command = build_wattle_tui_command(
        _args(
            wattle_provider_request_timeout_sec=None,
            wattle_stream_idle_timeout_sec=None,
        )
    )

    assert "WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS" not in command
    assert "WATTLE_STREAM_IDLE_TIMEOUT_SECONDS" not in command


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
