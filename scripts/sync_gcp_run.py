#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_PROJECT = "terminal-bench-for-wattle"
DEFAULT_ZONE = "us-central1-a"
DEFAULT_INSTANCE = "tbench-amd64"
DEFAULT_REMOTE_REPO = "/home/liyuan/repos/wattle-tbench-harness"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync a GCP TBench run back to this machine for analysis."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--zone", default=DEFAULT_ZONE)
    parser.add_argument("--instance", default=DEFAULT_INSTANCE)
    parser.add_argument("--remote-repo", default=DEFAULT_REMOTE_REPO)
    parser.add_argument(
        "--run-label",
        default="latest",
        help="Run label to sync, or 'latest' to use the VM's runs/latest symlink.",
    )
    parser.add_argument("--local-dir", type=Path, default=Path("runs/gcp"))
    parser.add_argument(
        "--method",
        choices=("rsync", "scp"),
        default="rsync",
        help="Transfer method. rsync is incremental and preferred for active runs.",
    )
    parser.add_argument("--no-analysis", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gcloud = shutil.which("gcloud") or str(
        Path.home() / ".local/google-cloud-sdk-install/google-cloud-sdk/bin/gcloud"
    )
    if not Path(gcloud).exists() and shutil.which("gcloud") is None:
        print("[error] gcloud not found on PATH or local SDK install path.", file=sys.stderr)
        return 2

    run_label = args.run_label
    if run_label == "latest":
        run_label = remote_latest_label(
            gcloud=gcloud,
            project=args.project,
            zone=args.zone,
            instance=args.instance,
            remote_repo=args.remote_repo,
        )

    local_run_dir = args.local_dir.expanduser().resolve() / run_label
    local_run_dir.parent.mkdir(parents=True, exist_ok=True)
    remote_run_dir = f"{args.remote_repo.rstrip('/')}/runs/{run_label}"

    if args.method == "rsync":
        sync_with_rsync(
            gcloud=gcloud,
            project=args.project,
            zone=args.zone,
            instance=args.instance,
            remote_run_dir=remote_run_dir,
            local_run_dir=local_run_dir,
        )
    else:
        scp_cmd = [
            gcloud,
            "compute",
            "scp",
            "--recurse",
            f"{args.instance}:{remote_run_dir}",
            str(local_run_dir.parent),
            f"--project={args.project}",
            f"--zone={args.zone}",
        ]
        run(scp_cmd)

    if not args.no_analysis:
        repo = Path(__file__).resolve().parents[1]
        run([sys.executable, str(repo / "scripts/generate_reports.py"), str(local_run_dir)])
        run([sys.executable, str(repo / "scripts/incremental_tbench_analysis.py"), str(local_run_dir)])

    print(f"Synced run: {local_run_dir}")
    if not args.no_analysis:
        print(f"Reports: {local_run_dir / 'reports/summary.md'}")
        print(f"Incremental analysis: {local_run_dir / 'analysis/incremental/summary.md'}")
    return 0


def remote_latest_label(
    *,
    gcloud: str,
    project: str,
    zone: str,
    instance: str,
    remote_repo: str,
) -> str:
    command = (
        "set -e; "
        f"cd {shlex.quote(remote_repo)}; "
        "if [ -f runs/.last_run_label ]; then "
        "cat runs/.last_run_label; "
        "elif [ -L runs/latest ]; then "
        "basename \"$(readlink runs/latest)\"; "
        "else "
        "ls -1td runs/*/jobs 2>/dev/null | head -n 1 | cut -d/ -f2; "
        "fi"
    )
    ssh_cmd = [
        gcloud,
        "compute",
        "ssh",
        instance,
        f"--project={project}",
        f"--zone={zone}",
        "--command",
        command,
    ]
    proc = subprocess.run(ssh_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)
    label = proc.stdout.strip().splitlines()[-1].strip()
    if not label:
        print("[error] Could not infer latest remote run label.", file=sys.stderr)
        raise SystemExit(2)
    return label


def sync_with_rsync(
    *,
    gcloud: str,
    project: str,
    zone: str,
    instance: str,
    remote_run_dir: str,
    local_run_dir: Path,
) -> None:
    if shutil.which("rsync") is None:
        print("[error] rsync not found locally; rerun with --method scp.", file=sys.stderr)
        raise SystemExit(2)

    dry_run_cmd = [
        gcloud,
        "compute",
        "ssh",
        instance,
        f"--project={project}",
        f"--zone={zone}",
        "--dry-run",
    ]
    proc = subprocess.run(dry_run_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)

    ssh_parts = shlex.split(proc.stdout.strip())
    if len(ssh_parts) < 2:
        print("[error] Could not parse gcloud SSH dry-run command.", file=sys.stderr)
        raise SystemExit(2)
    remote = ssh_parts[-1]
    ssh_command_parts = [part for part in ssh_parts[:-1] if part != "-t"]
    ssh_command = " ".join(shlex.quote(part) for part in ssh_command_parts)

    local_run_dir.mkdir(parents=True, exist_ok=True)
    rsync_cmd = [
        "rsync",
        "-az",
        "--delete",
        "--filter=P /analysis/failure_analysis/***",
        "--filter=P /analysis/failure_analysis",
        "--info=stats2,progress2",
        "-e",
        ssh_command,
        f"{remote}:{remote_run_dir.rstrip('/')}/",
        f"{local_run_dir}/",
    ]
    run(rsync_cmd)


def run(command: list[str]) -> None:
    print("$", " ".join(shlex.quote(part) for part in command))
    subprocess.run(command, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
