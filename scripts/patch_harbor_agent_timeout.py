#!/usr/bin/env python3
from __future__ import annotations

import inspect
import shutil
from pathlib import Path

from harbor.trial.trial import Trial

PATCH_MARKER = 'extra_kwargs["agent_timeout_sec"] = self._agent_timeout_sec'


def main() -> int:
    source_path = Path(inspect.getsourcefile(Trial) or "")
    if not source_path.exists():
        print("Could not locate Harbor Trial source file.")
        return 1

    text = source_path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        print(f"Already patched: {source_path}")
        return 0

    old = """        if self.config.agent.name == AgentName.ORACLE.value:
            extra_kwargs = {
                "task_dir": self.task.task_dir,
                "trial_paths": self.paths,
                "agent_timeout_sec": self._agent_timeout_sec,
            }
        mcp_servers = {
"""
    new = """        if self.config.agent.name == AgentName.ORACLE.value:
            extra_kwargs = {
                "task_dir": self.task.task_dir,
                "trial_paths": self.paths,
                "agent_timeout_sec": self._agent_timeout_sec,
            }
        if self._agent_timeout_sec is not None:
            extra_kwargs["agent_timeout_sec"] = self._agent_timeout_sec
        mcp_servers = {
"""
    patched = text.replace(old, new)
    if patched == text:
        print(f"Could not find Trial._init_agent insertion point in {source_path}")
        print("Harbor may have changed. Inspect harbor.trial.trial.Trial._init_agent.")
        return 1

    backup_path = source_path.with_suffix(source_path.suffix + ".agent-timeout.bak")
    if not backup_path.exists():
        shutil.copy2(source_path, backup_path)
        print(f"Backed up original file to {backup_path}")

    source_path.write_text(patched, encoding="utf-8")
    print(f"Patched Harbor Trial._init_agent in {source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
