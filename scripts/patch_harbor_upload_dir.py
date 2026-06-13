#!/usr/bin/env python3
from __future__ import annotations

import inspect
import shutil
from pathlib import Path

from harbor.environments.docker import docker_unix

PATCH_MARKERS = (
    'f"{source_dir}/."',
    'str(source_dir).rstrip("/") + "/."',
    "str(source_dir).rstrip('/') + '/.'",
)


def main() -> int:
    source_path = Path(inspect.getsourcefile(docker_unix.UnixOps) or "")
    if not source_path.exists():
        print("Could not locate Harbor UnixOps source file.")
        return 1

    text = source_path.read_text(encoding="utf-8")
    if any(marker in text for marker in PATCH_MARKERS):
        print(f"Already patched: {source_path}")
        return 0

    replacements = [
        (
            '["cp", str(source_dir), f"main:{target_dir}"]',
            '["cp", f"{source_dir}/.", f"main:{target_dir}"]',
        ),
        (
            """[
                "cp",
                str(source_dir),
                f"main:{target_dir}",
            ]""",
            """[
                "cp",
                f"{source_dir}/.",
                f"main:{target_dir}",
            ]""",
        ),
    ]

    patched = text
    for old, new in replacements:
        patched = patched.replace(old, new)

    if patched == text:
        print(f"Could not find an unpatched docker cp upload_dir in {source_path}")
        print("Harbor may have changed. Inspect harbor.environments.docker.docker_unix.")
        return 1

    backup_path = source_path.with_suffix(source_path.suffix + ".bak")
    if not backup_path.exists():
        shutil.copy2(source_path, backup_path)
        print(f"Backed up original file to {backup_path}")

    source_path.write_text(patched, encoding="utf-8")
    print(f"Patched Harbor UnixOps.upload_dir in {source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

