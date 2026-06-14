from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from model_config import ParsedModel, parse_codex_model


class CodexAgent(BaseInstalledAgent):
    """Harbor adapter that runs the Codex CLI against Terminal-Bench tasks."""

    _OUTPUT_FILENAME = "codex-output.jsonl"
    _EXIT_STATUS_FILENAME = "codex-exit-status.txt"
    _REMOTE_INSTALL_DIR = "/installed-agent"

    @staticmethod
    def name() -> str:
        return "codex"

    def __init__(
        self,
        *args: Any,
        codex_auth_path: str | None = None,
        codex_config_path: str | None = None,
        agent_timeout_sec: int | float | str | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.codex_auth_path = _resolve_optional_path(
            codex_auth_path or os.environ.get("CODEX_AUTH_PATH")
        )
        self.codex_config_path = _resolve_optional_path(
            codex_config_path or os.environ.get("CODEX_CONFIG_PATH")
        )
        self.agent_timeout_sec = _normalize_optional_number(
            agent_timeout_sec,
            "agent_timeout_sec",
        )
        self._parsed_model: ParsedModel = parse_codex_model(self.model_name)

    def get_version_command(self) -> str | None:
        return "codex --version"

    async def install(self, environment: BaseEnvironment) -> None:
        await environment.exec(command=f"mkdir -p {self._REMOTE_INSTALL_DIR}", user="root")
        await self._upload_auth_files(environment)
        await self.exec_as_root(
            environment,
            command=(
                "set -euo pipefail; "
                "export DEBIAN_FRONTEND=noninteractive; "
                "apt-get update && "
                "apt-get install -y --no-install-recommends "
                "ca-certificates curl git gnupg && "
                "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && "
                "apt-get install -y --no-install-recommends nodejs && "
                "npm install -g @openai/codex && "
                "apt-get clean && rm -rf /var/lib/apt/lists/*"
            ),
        )
        await self.exec_as_agent(environment, command=self._auth_setup_command())

    async def _upload_auth_files(self, environment: BaseEnvironment) -> None:
        if self.codex_auth_path is not None:
            await environment.upload_file(
                self.codex_auth_path,
                f"{self._REMOTE_INSTALL_DIR}/codex-auth.json",
            )
        if self.codex_config_path is not None:
            await environment.upload_file(
                self.codex_config_path,
                f"{self._REMOTE_INSTALL_DIR}/codex-config.toml",
            )

    def _auth_setup_command(self) -> str:
        return f"""
set -euo pipefail
mkdir -p "$HOME/.codex"
chmod 700 "$HOME/.codex"
if [ -f {self._REMOTE_INSTALL_DIR}/codex-auth.json ]; then
  cp {self._REMOTE_INSTALL_DIR}/codex-auth.json "$HOME/.codex/auth.json"
  chmod 600 "$HOME/.codex/auth.json"
fi
if [ -f {self._REMOTE_INSTALL_DIR}/codex-config.toml ]; then
  cp {self._REMOTE_INSTALL_DIR}/codex-config.toml "$HOME/.codex/config.toml"
  chmod 600 "$HOME/.codex/config.toml"
fi
command -v codex >/dev/null
"""

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await self.exec_as_agent(environment, command=self._build_codex_command(instruction))
        self.populate_context_post_run(context)

    def _build_codex_command(self, instruction: str) -> str:
        cmd = [
            "codex",
            "exec",
            "--json",
            "-m",
            self._parsed_model.model,
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "-C",
            "/app",
            instruction,
        ]
        run_command = shlex.join(cmd)
        if self.agent_timeout_sec is not None:
            timeout_sec = shlex.quote(str(self.agent_timeout_sec))
            run_command = f"timeout --preserve-status {timeout_sec}s {run_command}"

        return (
            "set -euo pipefail; "
            "mkdir -p /logs/agent; "
            "date -Iseconds > /logs/agent/codex-started-at.txt; "
            f"{run_command} 2>&1 | tee /logs/agent/{self._OUTPUT_FILENAME}; "
            "run_status=${PIPESTATUS[0]}; "
            f"printf '%s\\n' \"$run_status\" > /logs/agent/{self._EXIT_STATUS_FILENAME}; "
            "date -Iseconds > /logs/agent/codex-ended-at.txt; "
            "exit \"$run_status\""
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        output_path = self.logs_dir / self._OUTPUT_FILENAME
        input_tokens, cache_tokens, output_tokens = _usage_from_codex_jsonl(output_path)
        context.n_input_tokens = input_tokens
        context.n_cache_tokens = cache_tokens
        context.n_output_tokens = output_tokens
        context.metadata = {
            "agent": "codex",
            "raw_model": self._parsed_model.raw,
            "provider": self._parsed_model.provider,
            "model": self._parsed_model.model,
            "agent_timeout_sec": self.agent_timeout_sec,
            "output_file": str(output_path),
        }


def _usage_from_codex_jsonl(path: Path) -> tuple[int, int, int]:
    total_input = 0
    total_cached = 0
    total_output = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, 0, 0

    for line in lines:
        if not line.strip().startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = _find_usage(event)
        if not usage:
            continue
        total_input += _int_field(usage, "input_tokens", "prompt_tokens")
        total_cached += _int_field(usage, "cached_tokens", "cached_input_tokens")
        total_output += _int_field(usage, "output_tokens", "completion_tokens")
    return total_input, total_cached, total_output


def _find_usage(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        usage = value.get("usage") or value.get("token_usage")
        if isinstance(usage, dict):
            return usage
        for item in value.values():
            found = _find_usage(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage(item)
            if found is not None:
                return found
    return None


def _int_field(data: dict[str, Any], *names: str) -> int:
    for name in names:
        value = data.get(name)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _normalize_optional_number(value: int | float | str | None, name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc


def _resolve_optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.exists() else None
