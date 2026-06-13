#!/usr/bin/env python3
from __future__ import annotations

import inspect

from harbor.environments.docker.docker_unix import UnixOps


def main() -> int:
    source = inspect.getsource(UnixOps.upload_dir)
    if 'f"{source_dir}/."' in source or 'rstrip("/") + "/."' in source:
        print("PATCHED: UnixOps.upload_dir copies directory contents.")
        return 0
    print("NOT PATCHED: run scripts/patch_harbor_upload_dir.py before evaluations.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

