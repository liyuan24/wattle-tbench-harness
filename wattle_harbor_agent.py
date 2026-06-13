from __future__ import annotations

import json
import os
import shlex
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from model_config import ParsedModel, parse_provider_model

EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
PROVIDER_API_KEY_ENVS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
}


class WattleAgent(BaseInstalledAgent):
    """Harbor adapter that runs Wattle against Terminal-Bench 2.0 tasks."""

    _OUTPUT_FILENAME = "wattle-output.log"
    _EXIT_STATUS_FILENAME = "wattle-exit-status.txt"
    _REMOTE_INSTALL_DIR = "/installed-agent"
    _REMOTE_SESSION_DIR = "/logs/agent/wattle-sessions"

    @staticmethod
    def name() -> str:
        return "wattle"

    def __init__(
        self,
        *args: Any,
        provider: str | None = None,
        thinking: bool | str = True,
        effort: str | None = "high",
        max_tokens: int | str | None = None,
        provider_request_timeout_seconds: int | float | str | None = None,
        stream_idle_timeout_seconds: int | float | str | None = None,
        source_dir: str | None = None,
        wattle_auth_path: str | None = None,
        codex_auth_path: str | None = None,
        codex_config_path: str | None = None,
        wattle_git_url: str = "https://github.com/liyuan24/wattle.git",
        wattle_git_ref: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.thinking = _parse_bool(thinking)
        self.effort = _normalize_effort(effort)
        self.max_tokens = _normalize_optional_int(max_tokens, "max_tokens")
        self.provider_request_timeout_seconds = _normalize_optional_number(
            provider_request_timeout_seconds,
            "provider_request_timeout_seconds",
        )
        self.stream_idle_timeout_seconds = _normalize_optional_number(
            stream_idle_timeout_seconds,
            "stream_idle_timeout_seconds",
        )
        if self.stream_idle_timeout_seconds is None:
            self.stream_idle_timeout_seconds = self.provider_request_timeout_seconds
        self.source_dir = _resolve_optional_path(source_dir or os.environ.get("WATTLE_SOURCE_DIR"))
        self.wattle_auth_path = _resolve_optional_path(
            wattle_auth_path or os.environ.get("WATTLE_AUTH_PATH")
        )
        self.codex_auth_path = _resolve_optional_path(
            codex_auth_path or os.environ.get("CODEX_AUTH_PATH")
        )
        self.codex_config_path = _resolve_optional_path(
            codex_config_path or os.environ.get("CODEX_CONFIG_PATH")
        )
        self.wattle_git_url = wattle_git_url
        self.wattle_git_ref = wattle_git_ref
        self._parsed_model: ParsedModel = parse_provider_model(self.model_name, provider=provider)

    def get_version_command(self) -> str | None:
        return (
            "python3 - <<'PY'\n"
            "from importlib.metadata import version\n"
            "print(version('wattle'))\n"
            "PY"
        )

    async def install(self, environment: BaseEnvironment) -> None:
        await environment.exec(command=f"mkdir -p {self._REMOTE_INSTALL_DIR}", user="root")
        await self._upload_auth_files(environment)

        source_archive: Path | None = None
        try:
            if self.source_dir is not None:
                source_archive = _build_source_archive(self.source_dir)
                await environment.upload_file(
                    source_archive,
                    f"{self._REMOTE_INSTALL_DIR}/wattle-source.tgz",
                )
                install_source = "local"
            else:
                install_source = "git"

            await self.exec_as_root(
                environment,
                command=(
                    "set -euo pipefail; "
                    "export DEBIAN_FRONTEND=noninteractive; "
                    "apt-get update && "
                    "apt-get install -y --no-install-recommends "
                    "ca-certificates curl git python3 python3-venv tar gzip && "
                    "apt-get clean && rm -rf /var/lib/apt/lists/*"
                ),
            )
            await self.exec_as_agent(
                environment,
                command=self._install_command(install_source),
            )
        finally:
            if source_archive is not None:
                source_archive.unlink(missing_ok=True)

    async def _upload_auth_files(self, environment: BaseEnvironment) -> None:
        temp_auth_path: Path | None = None
        try:
            if self.wattle_auth_path is not None:
                await environment.upload_file(
                    self.wattle_auth_path,
                    f"{self._REMOTE_INSTALL_DIR}/wattle-auth.json",
                )
            else:
                wattle_auth = _build_wattle_auth_from_environment()
                if self.codex_auth_path is not None:
                    oauth = _wattle_openai_oauth_from_codex_auth(self.codex_auth_path)
                    if oauth:
                        wattle_auth.setdefault("openai", {"oauth": oauth})
                if wattle_auth:
                    temp_auth_path = _write_temp_json(wattle_auth, prefix="wattle-auth-")
                    await environment.upload_file(
                        temp_auth_path,
                        f"{self._REMOTE_INSTALL_DIR}/wattle-auth.json",
                    )

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
        finally:
            if temp_auth_path is not None:
                temp_auth_path.unlink(missing_ok=True)

    def _install_command(self, install_source: str) -> str:
        if install_source == "local":
            install_wattle = (
                "rm -rf /tmp/wattle-src && "
                "mkdir -p /tmp/wattle-src && "
                f"tar -xzf {self._REMOTE_INSTALL_DIR}/wattle-source.tgz -C /tmp/wattle-src && "
                "uv --no-cache tool install --force -e /tmp/wattle-src"
            )
        else:
            ref = self.wattle_git_ref
            if not ref:
                raise ValueError("wattle_git_ref is required when source_dir is not provided")
            install_wattle = (
                "uv --no-cache tool install --force "
                f"git+{shlex.quote(self.wattle_git_url)}@{shlex.quote(ref)}"
            )

        auth_setup = f"""
mkdir -p "$HOME/.wattle" "$HOME/.codex"
chmod 700 "$HOME/.wattle" "$HOME/.codex"
if [ -f {self._REMOTE_INSTALL_DIR}/wattle-auth.json ]; then
  cp {self._REMOTE_INSTALL_DIR}/wattle-auth.json "$HOME/.wattle/auth.json"
  chmod 600 "$HOME/.wattle/auth.json"
fi
if [ -f {self._REMOTE_INSTALL_DIR}/codex-auth.json ]; then
  cp {self._REMOTE_INSTALL_DIR}/codex-auth.json "$HOME/.codex/auth.json"
  chmod 600 "$HOME/.codex/auth.json"
fi
if [ -f {self._REMOTE_INSTALL_DIR}/codex-config.toml ]; then
  cp {self._REMOTE_INSTALL_DIR}/codex-config.toml "$HOME/.codex/config.toml"
  chmod 600 "$HOME/.codex/config.toml"
fi
"""
        return f"""
set -euo pipefail
export UV_CACHE_DIR=/tmp/uv-cache
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
{auth_setup}
{install_wattle}
rm -rf /tmp/uv-cache
command -v wattle >/dev/null
"""

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        await self.exec_as_agent(environment, command=self._build_wattle_command(instruction))
        self.populate_context_post_run(context)

    def _build_wattle_command(self, instruction: str) -> str:
        cmd = [
            "wattle",
            "--provider",
            self._parsed_model.provider,
            "--model",
            self._parsed_model.model,
            "--persist",
            "--yolo",
        ]
        if self.max_tokens is not None:
            cmd.extend(["--max-tokens", str(self.max_tokens)])
        if self.thinking:
            cmd.append("--thinking")
        if self.effort:
            cmd.extend(["--effort", self.effort])
        cmd.extend(["-p", instruction])

        timeout_export = ""
        if self.provider_request_timeout_seconds is not None:
            timeout_export = (
                "export WATTLE_PROVIDER_REQUEST_TIMEOUT_SECONDS="
                f"{shlex.quote(str(self.provider_request_timeout_seconds))}; "
            )
        if self.stream_idle_timeout_seconds is not None:
            timeout_export += (
                "export WATTLE_STREAM_IDLE_TIMEOUT_SECONDS="
                f"{shlex.quote(str(self.stream_idle_timeout_seconds))}; "
            )

        return (
            "set -euo pipefail; "
            f"mkdir -p {self._REMOTE_SESSION_DIR}; "
            'export PATH="$HOME/.local/bin:$PATH"; '
            f"export WATTLE_SESSION_DIR={self._REMOTE_SESSION_DIR}; "
            f"{timeout_export}"
            "date -Iseconds > /logs/agent/wattle-started-at.txt; "
            f"{shlex.join(cmd)} 2>&1 | tee /logs/agent/{self._OUTPUT_FILENAME}; "
            "run_status=${PIPESTATUS[0]}; "
            f"printf '%s\\n' \"$run_status\" > /logs/agent/{self._EXIT_STATUS_FILENAME}; "
            "date -Iseconds > /logs/agent/wattle-ended-at.txt; "
            "exit \"$run_status\""
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        total_input = 0
        total_output = 0
        total_cached = 0
        session_files = sorted((self.logs_dir / "wattle-sessions").glob("*.jsonl"))

        for session_file in session_files:
            try:
                for line in session_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get("type") != "message":
                        continue
                    message = item.get("message") or {}
                    if message.get("role") != "assistant":
                        continue
                    total_input += int(message.get("input_tokens") or 0)
                    total_output += int(message.get("output_tokens") or 0)
                    total_cached += int(message.get("cached_tokens") or 0)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                self.logger.exception("Failed to parse Wattle session file %s", session_file)

        context.n_input_tokens = total_input
        context.n_output_tokens = total_output
        context.n_cache_tokens = total_cached
        context.metadata = {
            "agent": "wattle",
            "raw_model": self._parsed_model.raw,
            "provider": self._parsed_model.provider,
            "model": self._parsed_model.model,
            "thinking": self.thinking,
            "effort": self.effort or "none",
            "max_tokens": self.max_tokens,
            "provider_request_timeout_seconds": self.provider_request_timeout_seconds,
            "stream_idle_timeout_seconds": self.stream_idle_timeout_seconds,
            "session_files": [str(path) for path in session_files],
        }


def _parse_bool(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_effort(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"", "none", "false", "off"}:
        return None
    if normalized not in EFFORTS:
        choices = ", ".join(sorted(EFFORTS))
        raise ValueError(f"Unsupported effort '{value}'. Supported: {choices}")
    return normalized


def _normalize_optional_int(value: int | str | None, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


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


def _build_wattle_auth_from_environment() -> dict[str, Any]:
    auth: dict[str, Any] = {}
    codex_oauth_token = os.environ.get("CODEX_OAUTH_TOKEN")
    if codex_oauth_token:
        auth["openai"] = {"oauth": _parse_codex_oauth_token(codex_oauth_token)}
    elif openai_api_key := os.environ.get("OPENAI_API_KEY"):
        auth["openai"] = {"api_key": {"api_key": openai_api_key}}

    for provider, env_name in PROVIDER_API_KEY_ENVS.items():
        if api_key := os.environ.get(env_name):
            auth[provider] = {"api_key": {"api_key": api_key}}
    return auth


def _parse_codex_oauth_token(value: str) -> dict[str, Any]:
    stripped = value.strip()
    if stripped.startswith("{"):
        oauth = json.loads(stripped)
        if not isinstance(oauth, dict):
            raise ValueError("CODEX_OAUTH_TOKEN JSON value must be an object")
        if not isinstance(oauth.get("access_token"), str) or not oauth["access_token"]:
            raise ValueError("CODEX_OAUTH_TOKEN JSON value must include access_token")
        return oauth
    return {"access_token": value}


def _wattle_openai_oauth_from_codex_auth(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    candidates: list[Any] = []
    if isinstance(data, dict):
        candidates.extend([data.get("tokens"), data])
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                candidates.extend([item.get("tokens"), item])

    for candidate in candidates:
        if isinstance(candidate, dict) and isinstance(candidate.get("access_token"), str):
            return candidate
    return None


def _write_temp_json(data: dict[str, Any], prefix: str) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix=prefix, suffix=".json")
    path = Path(raw_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        path.chmod(0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _build_source_archive(source_dir: Path) -> Path:
    if not source_dir.exists():
        raise FileNotFoundError(f"Wattle source dir not found: {source_dir}")

    fd, raw_path = tempfile.mkstemp(prefix="wattle-source-", suffix=".tgz")
    os.close(fd)
    archive = Path(raw_path)
    excludes = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "runs",
    }

    def include(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(tarinfo.name).parts
        return None if any(part in excludes for part in parts) else tarinfo

    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source_dir, arcname=".", filter=include)
    return archive
