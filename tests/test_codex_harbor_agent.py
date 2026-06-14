from __future__ import annotations

import json
from pathlib import Path

from codex_harbor_agent import CodexAgent, _usage_from_codex_jsonl


def test_codex_command_runs_codex_exec_without_wattle() -> None:
    agent = CodexAgent(logs_dir=Path("."), model_name="gpt-5.5")

    command = agent._build_codex_command("solve it")

    assert "codex exec --json" in command
    assert "-m gpt-5.5" in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--skip-git-repo-check" in command
    assert "-C /app" in command
    assert "solve it" in command
    assert "codex-output.jsonl" in command
    assert "wattle" not in command.lower()


def test_codex_command_can_use_harbor_agent_timeout() -> None:
    agent = CodexAgent(logs_dir=Path("."), model_name="codex/gpt-5.5", agent_timeout_sec=900)

    command = agent._build_codex_command("solve it")

    assert "timeout --preserve-status 900.0s codex exec" in command
    assert "-m gpt-5.5" in command


def test_codex_auth_setup_only_copies_codex_files() -> None:
    agent = CodexAgent(logs_dir=Path("."), model_name="gpt-5.5")

    command = agent._auth_setup_command()

    assert "$HOME/.codex" in command
    assert "codex-auth.json" in command
    assert "codex-config.toml" in command
    assert ".wattle" not in command


def test_usage_from_codex_jsonl_extracts_token_counts(tmp_path: Path) -> None:
    path = tmp_path / "codex-output.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "event",
                        "usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 3,
                            "output_tokens": 4,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "nested",
                        "payload": {
                            "usage": {
                                "prompt_tokens": 7,
                                "cached_tokens": 2,
                                "completion_tokens": 5,
                            }
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    assert _usage_from_codex_jsonl(path) == (17, 5, 9)
