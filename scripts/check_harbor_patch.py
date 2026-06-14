#!/usr/bin/env python3
from __future__ import annotations

import inspect

from harbor.environments.docker.docker_unix import UnixOps
from harbor.trial.trial import Trial


def main() -> int:
    upload_dir_source = inspect.getsource(UnixOps.upload_dir)
    upload_dir_patched = (
        'f"{source_dir}/."' in upload_dir_source
        or 'rstrip("/") + "/."' in upload_dir_source
    )
    timeout_source = inspect.getsource(Trial._init_agent)
    timeout_patched = (
        'extra_kwargs["agent_timeout_sec"] = self._agent_timeout_sec' in timeout_source
    )

    if upload_dir_patched:
        print("PATCHED: UnixOps.upload_dir copies directory contents.")
    else:
        print("NOT PATCHED: run scripts/patch_harbor_upload_dir.py before evaluations.")

    if timeout_patched:
        print("PATCHED: Trial._init_agent passes agent_timeout_sec to agents.")
    else:
        print(
            "NOT PATCHED: run scripts/patch_harbor_agent_timeout.py before evaluations."
        )

    return 0 if upload_dir_patched and timeout_patched else 1


if __name__ == "__main__":
    raise SystemExit(main())
