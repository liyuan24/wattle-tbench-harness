from __future__ import annotations

import shlex
from pathlib import Path

from terminal_bench.agents.base_agent import AgentResult
from terminal_bench.agents.failure_mode import FailureMode
from terminal_bench.agents.installed_agents.abstract_installed_agent import (
    AbstractInstalledAgent,
)
from terminal_bench.terminal.models import TerminalCommand
from terminal_bench.terminal.tmux_session import TmuxSession


class CodexInstalledAgent(AbstractInstalledAgent):
    @staticmethod
    def name() -> str:
        return "codex"

    def __init__(
        self,
        model_name: str | None = None,
        model: str = "gpt-5.5",
        effort: str | None = "none",
        auth_path: str = "/home/liyuan/.codex/auth.json",
        codex_config_path: str = "/home/liyuan/.codex/config.toml",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.model = (model_name or model).split("/")[-1]
        self.effort = effort if effort not in {"", "none", "None"} else None
        self.auth_path = Path(auth_path).expanduser()
        self.codex_config_path = Path(codex_config_path).expanduser()

    @property
    def _env(self) -> dict[str, str]:
        return {}

    @property
    def _install_agent_script_path(self) -> Path:
        return Path(__file__).parent / "setup-codex.sh"

    def perform_task(
        self,
        instruction: str,
        session: TmuxSession,
        logging_dir: Path | None = None,
    ) -> AgentResult:
        session.copy_to_container(
            self._install_agent_script_path,
            container_dir="/installed-agent",
            container_filename="install-agent.sh",
        )
        session.copy_to_container(
            self.auth_path,
            container_dir="/installed-agent",
            container_filename="codex-auth.json",
        )
        if self.codex_config_path.exists():
            session.copy_to_container(
                self.codex_config_path,
                container_dir="/installed-agent",
                container_filename="codex-config.toml",
            )

        session.send_keys(
            [
                (
                    "source /installed-agent/install-agent.sh || "
                    "echo 'INSTALL_FAIL_STATUS'"
                ),
                "Enter",
            ],
            block=True,
            max_timeout_sec=float("inf"),
        )

        if "INSTALL_FAIL_STATUS" in session.capture_pane().split("\n"):
            return AgentResult(
                total_input_tokens=0,
                total_output_tokens=0,
                failure_mode=FailureMode.AGENT_INSTALLATION_FAILED,
            )

        rendered_instruction = self._render_instruction(instruction)
        for command in self._run_agent_commands(rendered_instruction):
            session.send_command(command)

        return AgentResult(total_input_tokens=0, total_output_tokens=0)

    def _run_agent_commands(self, instruction: str) -> list[TerminalCommand]:
        cmd = [
            "codex",
            "exec",
            "-C",
            "/app",
            "-m",
            self.model,
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json",
        ]
        if self.effort:
            cmd.extend(["-c", f'model_reasoning_effort="{self.effort}"'])
        cmd.append("-")

        inner = (
            "set -o pipefail; "
            "mkdir -p /agent-logs; "
            "export PATH=\"$HOME/.local/bin:$PATH\"; "
            f"printf %s {shlex.quote(instruction)} | "
            f"{shlex.join(cmd)} "
            "2> >(tee /agent-logs/codex-stderr.log >&2) "
            "| tee /agent-logs/codex-events.jsonl; "
            "status=${PIPESTATUS[1]}; "
            "printf '%s\n' \"$status\" > /agent-logs/codex-exit-status.txt; "
            "cat /agent-logs/codex-events.jsonl /agent-logs/codex-stderr.log "
            "> /agent-logs/codex-output.log 2>/dev/null || true; "
            "exit 0"
        )
        return [
            TerminalCommand(
                command=f"bash -lc {shlex.quote(inner)}",
                min_timeout_sec=0.0,
                max_timeout_sec=float("inf"),
                block=True,
                append_enter=True,
            )
        ]
