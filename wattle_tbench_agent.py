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


class WattleInstalledAgent(AbstractInstalledAgent):
    @staticmethod
    def name() -> str:
        return "wattle"

    def __init__(
        self,
        provider: str = "openai_codex",
        model_name: str | None = None,
        model: str = "gpt-5.5",
        thinking: bool | str = False,
        effort: str | None = None,
        max_tokens: int = 4096,
        source_tgz_path: str = "/home/liyuan/repos/wattle-tbench-harness/wattle-source.tgz",
        wattle_auth_path: str = "/home/liyuan/.wattle/auth.json",
        codex_auth_path: str = "/home/liyuan/.codex/auth.json",
        codex_config_path: str = "/home/liyuan/.codex/config.toml",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.provider = provider
        self.model = (model_name or model).split("/")[-1]
        self.thinking = _bool_value(thinking)
        self.effort = effort if effort not in {"", "none", "None"} else None
        self.max_tokens = int(max_tokens)
        self.source_tgz_path = Path(source_tgz_path).expanduser()
        self.wattle_auth_path = Path(wattle_auth_path).expanduser()
        self.codex_auth_path = Path(codex_auth_path).expanduser()
        self.codex_config_path = Path(codex_config_path).expanduser()

    @property
    def _env(self) -> dict[str, str]:
        return {}

    @property
    def _install_agent_script_path(self) -> Path:
        return Path(__file__).parent / "setup.sh"

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
            self.source_tgz_path,
            container_dir="/installed-agent",
            container_filename="wattle-source.tgz",
        )
        if self.wattle_auth_path.exists():
            session.copy_to_container(
                self.wattle_auth_path,
                container_dir="/installed-agent",
                container_filename="wattle-auth.json",
            )
        if self.codex_auth_path.exists():
            session.copy_to_container(
                self.codex_auth_path,
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
            "wattle",
            "--provider",
            self.provider,
            "--model",
            self.model,
            "--max-tokens",
            str(self.max_tokens),
            "--persist",
            "--yolo",
        ]
        if self.thinking:
            cmd.append("--thinking")
        if self.effort:
            cmd.extend(["--effort", self.effort])
        cmd.extend(["-p", instruction])

        inner = (
            "set -o pipefail; "
            "mkdir -p /agent-logs/wattle-sessions; "
            "export PATH=\"$HOME/.local/bin:$PATH\"; "
            "export WATTLE_SESSION_DIR=/agent-logs/wattle-sessions; "
            "date -Iseconds > /agent-logs/wattle-started-at.txt; "
            f"{shlex.join(cmd)} 2>&1 | tee /agent-logs/wattle-output.log; "
            "status=${PIPESTATUS[0]}; "
            "printf '%s\n' \"$status\" > /agent-logs/wattle-exit-status.txt; "
            "for session_file in /agent-logs/wattle-sessions/*.jsonl; do "
            "[ -f \"$session_file\" ] || continue; "
            "printf '\n__WATTLE_SESSION_JSONL_BEGIN__ %s\n' \"$session_file\"; "
            "cat \"$session_file\"; "
            "printf '__WATTLE_SESSION_JSONL_END__\n'; "
            "done; "
            "date -Iseconds > /agent-logs/wattle-ended-at.txt; "
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


def _bool_value(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}
