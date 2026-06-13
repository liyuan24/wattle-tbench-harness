from __future__ import annotations

import argparse
from pathlib import Path

from run_tui_task import build_start_env_command, build_wattle_tui_command


def _args(**overrides: object) -> argparse.Namespace:
    data = {
        "codex_auth_path": Path("/home/user/.codex/auth.json"),
        "codex_config_path": Path("/home/user/.codex/config.toml"),
        "effort": "high",
        "harbor_bin": Path("/bin/harbor"),
        "model": "deepseek/deepseek-v4-pro",
        "provider": None,
        "source_dir": Path("/src/wattle"),
        "task_name": "break-filter-js-from-html",
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
