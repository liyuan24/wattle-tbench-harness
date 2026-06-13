#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import sys

API_KEY_ENVS = {
    "ANTHROPIC_API_KEY",
    "CODEX_OAUTH_TOKEN",
    "DEEPSEEK_API_KEY",
    "KIMI_API_KEY",
    "MINIMAX_API_KEY",
    "OPENAI_API_KEY",
}


def main() -> int:
    target = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else ".env")
    exports = {name: os.environ[name] for name in sorted(API_KEY_ENVS) if os.environ.get(name)}

    lines = [
        "# Generated from current environment for wattle-tbench-harness.",
        "# Keep this file private and source it before running Harbor.",
    ]
    lines.extend(f"export {key}={shlex.quote(value)}" for key, value in sorted(exports.items()))
    lines.append("")

    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    os.chmod(target, 0o600)

    print(f"Wrote {target}")
    print("Exported: " + ", ".join(sorted(exports)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

