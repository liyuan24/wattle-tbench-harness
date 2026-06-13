from __future__ import annotations

from pathlib import Path

from wattle_harbor_agent import WattleAgent


def test_wattle_command_uses_provider_timeout_and_no_prompt_suffix() -> None:
    agent = WattleAgent(
        logs_dir=Path("."),
        model_name="deepseek/deepseek-v4-pro",
        provider_request_timeout_seconds=120,
        effort="high",
    )

    command = agent._build_wattle_command("solve it")

    assert "WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS=120.0" in command
    assert "WATTLE_STREAM_IDLE_TIMEOUT_SECONDS=120.0" in command
    assert "--provider deepseek" in command
    assert "--model deepseek-v4-pro" in command
    assert "--thinking" in command
    assert "--effort high" in command
    assert "solve it" in command
    assert "prompt suffix" not in command.lower()


def test_wattle_command_can_override_stream_idle_timeout() -> None:
    agent = WattleAgent(
        logs_dir=Path("."),
        model_name="deepseek/deepseek-v4-pro",
        provider_request_timeout_seconds=120,
        stream_idle_timeout_seconds=45,
        effort="high",
    )

    command = agent._build_wattle_command("solve it")

    assert "WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS=120.0" in command
    assert "WATTLE_STREAM_IDLE_TIMEOUT_SECONDS=45.0" in command


def test_wattle_command_omits_max_tokens_by_default() -> None:
    agent = WattleAgent(logs_dir=Path("."), model_name="deepseek/deepseek-v4-pro")

    command = agent._build_wattle_command("solve it")

    assert "--max-tokens" not in command
