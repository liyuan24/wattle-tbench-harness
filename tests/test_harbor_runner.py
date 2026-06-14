from __future__ import annotations

import argparse
from pathlib import Path

from model_config import parse_codex_model, parse_provider_model
from run_tbench import HarborRun, build_harbor_command, build_run


def test_parse_provider_model_supports_bare_model_with_provider() -> None:
    parsed = parse_provider_model("deepseek-v4-pro", provider="deepseek")

    assert parsed.raw == "deepseek/deepseek-v4-pro"
    assert parsed.provider == "deepseek"
    assert parsed.model == "deepseek-v4-pro"


def test_parse_provider_model_supports_combined_model() -> None:
    parsed = parse_provider_model("minimax/minimax-m2.7")

    assert parsed.raw == "minimax/minimax-m2.7"
    assert parsed.provider == "minimax"
    assert parsed.model == "minimax-m2.7"


def test_parse_codex_model_strips_provider_alias() -> None:
    parsed = parse_codex_model("codex/gpt-5.5")

    assert parsed.raw == "gpt-5.5"
    assert parsed.provider == "codex"
    assert parsed.model == "gpt-5.5"


def test_harbor_command_uses_terminal_bench_2_and_custom_agent() -> None:
    args = argparse.Namespace(
        agent="wattle",
        agent_env=[],
        agent_timeout_multiplier=None,
        dataset="terminal-bench@2.0",
        debug=False,
        effort="high",
        exclude_task_name=[],
        extra_harbor_arg=[],
        force_build=True,
        harbor_bin=Path("/bin/harbor"),
        include_task_name=["break-filter-js-from-html"],
        max_tokens=None,
        n_attempts=1,
        n_concurrent=2,
        n_tasks=None,
        no_delete=False,
        source_dir=Path("/src/wattle"),
        task=[],
        timeout_multiplier=None,
        verifier_timeout_multiplier=None,
        wattle_stream_idle_timeout_sec=90.0,
        wattle_auth_path=Path("/home/user/.wattle/auth.json"),
        codex_auth_path=Path("/home/user/.codex/auth.json"),
        codex_config_path=Path("/home/user/.codex/config.toml"),
        wattle_provider_request_timeout_sec=120.0,
    )
    run = HarborRun(
        name="wattle-deepseek-deepseek-v4-pro-high",
        job_name="wattle-deepseek-deepseek-v4-pro-high",
        model="deepseek/deepseek-v4-pro",
        provider="deepseek",
        model_name="deepseek-v4-pro",
    )

    command = build_harbor_command(args=args, run=run, job_dir=Path("/tmp/job"))

    assert command[:3] == ["/bin/harbor", "run", "-d"]
    assert "terminal-bench@2.0" in command
    assert "--agent-import-path" in command
    assert "wattle_harbor_agent:WattleAgent" in command
    assert "tb" not in command
    assert "terminal-bench-core==0.1.1" not in command
    assert "--include-task-name" in command
    assert "provider_request_timeout_seconds=120.0" in command
    assert "stream_idle_timeout_seconds=90.0" in command


def test_harbor_command_can_use_codex_agent_without_wattle_kwargs() -> None:
    args = argparse.Namespace(
        agent="codex",
        agent_env=[],
        agent_timeout_multiplier=None,
        dataset="terminal-bench@2.0",
        debug=False,
        effort="high",
        exclude_task_name=[],
        extra_harbor_arg=[],
        force_build=True,
        harbor_bin=Path("/bin/harbor"),
        include_task_name=["train-fasttext"],
        job_name=None,
        max_tokens=None,
        model="gpt-5.5",
        n_attempts=1,
        n_concurrent=2,
        n_tasks=None,
        no_delete=False,
        provider=None,
        source_dir=Path("/src/wattle"),
        task=[],
        timeout_multiplier=None,
        verifier_timeout_multiplier=None,
        wattle_stream_idle_timeout_sec=None,
        wattle_auth_path=Path("/home/user/.wattle/auth.json"),
        codex_auth_path=Path("/home/user/.codex/auth.json"),
        codex_config_path=Path("/home/user/.codex/config.toml"),
        wattle_provider_request_timeout_sec=None,
    )
    run = build_run(args)

    command = build_harbor_command(args=args, run=run, job_dir=Path("/tmp/job"))
    joined = " ".join(str(part) for part in command)

    assert run.name == "codex-codex-gpt-5.5-high-subset"
    assert "codex_harbor_agent:CodexAgent" in command
    assert "wattle_harbor_agent:WattleAgent" not in command
    assert "-m" in command
    assert "gpt-5.5" in command
    assert "codex_auth_path=/home/user/.codex/auth.json" in command
    assert "codex_config_path=/home/user/.codex/config.toml" in command
    assert "source_dir=" not in joined
    assert "wattle_auth_path=" not in joined
    assert "thinking=" not in joined
    assert "effort=high" not in joined
