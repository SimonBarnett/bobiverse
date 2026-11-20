#!/usr/bin/env python3
"""updatefleet — deploy bob-worker to every IRC digest machine (FR #8420).

Deterministic CLI. Discovers machines from GET /bob/v1/report (same set the
systray shows). Delegates WinRM + CredMan work to common/scripts/Update-BobFleet.ps1.
One JSON object on stdout. Exit 0=ok, 1=finding/partial fail, 2=error.
Never prints secrets.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _find_ps1() -> Path:
    env = (os.environ.get("BOB_UPDATEFLEET_PS1") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "common" / "scripts" / "Update-BobFleet.ps1",  # repo root
        here.parents[1] / "common" / "scripts" / "Update-BobFleet.ps1",
        Path(os.environ.get("BOB_AI_ROOT", r"C:\ai")) / "bob" / "common" / "scripts" / "Update-BobFleet.ps1",
        Path(os.environ.get("BOB_AI_ROOT", r"C:\ai")) / "bob" / "scripts" / "Update-BobFleet.ps1",
        Path(r"C:\ai\bob\common\scripts\Update-BobFleet.ps1"),
        Path(r"C:\ai\bob\scripts\Update-BobFleet.ps1"),
    ]
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    raise FileNotFoundError(
        "Update-BobFleet.ps1 not found; set BOB_UPDATEFLEET_PS1 or install under <ai>/bob/common/scripts"
    )


def _powershell() -> str:
    for name in ("powershell.exe", "powershell"):
        from shutil import which

        w = which(name)
        if w:
            return w
    return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="updatefleet",
        description="Update bob-worker on all IRC digest machines (FR #8420).",
    )
    ap.add_argument(
        "--store-credential",
        action="store_true",
        help="Prompt once and store wonderland\\administrator in CredMan Bobiverse/UpdateFleet",
    )
    ap.add_argument("--user", default="wonderland\\administrator", help="CredMan username")
    ap.add_argument("--artifact-dir", default="", help="Folder with bob-worker.exe (+ .sha256)")
    ap.add_argument(
        "--digest-url",
        default="https://bob.ntsa.uk/bob/v1/report",
        help="Digest report URL",
    )
    ap.add_argument("--ai-root", default="", help="Fleet ai root (default BOB_AI_ROOT or C:\\ai)")
    ap.add_argument(
        "--machine",
        action="append",
        default=[],
        help="Limit to machine id (repeatable); default = all digest machines",
    )
    ap.add_argument(
        "--skip-machine",
        action="append",
        default=[],
        help="Skip machine id (repeatable)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Plan only; no copy / WinRM mutate")
    ap.add_argument("--no-recycle", action="store_true", help="Install only; do not queue recycleseat")
    ap.add_argument(
        "--cred-target",
        default="Bobiverse/UpdateFleet",
        help="CredMan generic target name",
    )
    args = ap.parse_args(argv)

    try:
        ps1 = _find_ps1()
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "check": "updatefleet", "error": str(e)}))
        return 2

    cmd = [
        _powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
        "-User",
        args.user,
        "-CredTarget",
        args.cred_target,
        "-DigestUrl",
        args.digest_url,
    ]
    if args.store_credential:
        cmd.append("-StoreCredential")
    if args.artifact_dir:
        cmd.extend(["-ArtifactDir", args.artifact_dir])
    if args.ai_root:
        cmd.extend(["-AiRoot", args.ai_root])
    for m in args.machine:
        cmd.extend(["-Machine", m])
    for m in args.skip_machine:
        cmd.extend(["-SkipMachine", m])
    if args.dry_run:
        cmd.append("-DryRun")
    if args.no_recycle:
        cmd.append("-NoRecycle")

    # --store-credential uses Read-Host. capture_output pipes stdin, so the
    # prompt never reaches the console and CredMan can be stored empty.
    run_kwargs = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    if args.store_credential:
        run_kwargs["stdin"] = None
        run_kwargs["stdout"] = subprocess.PIPE
        run_kwargs["stderr"] = subprocess.PIPE
    else:
        run_kwargs["capture_output"] = True
    try:
        proc = subprocess.run(cmd, **run_kwargs)
    except OSError as e:
        print(json.dumps({"ok": False, "check": "updatefleet", "error": f"spawn: {e}"}))
        return 2

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out:
        # Print last non-empty line that looks like JSON (script may Write-Host warnings)
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        json_line = None
        for ln in reversed(lines):
            if ln.startswith("{") and ln.endswith("}"):
                json_line = ln
                break
        if json_line:
            print(json_line)
        else:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "check": "updatefleet",
                        "error": "no-json-stdout",
                        "stdout_tail": out[-500:],
                        "stderr_tail": err[-500:],
                        "exit": proc.returncode,
                    }
                )
            )
            return 2
    else:
        print(
            json.dumps(
                {
                    "ok": False,
                    "check": "updatefleet",
                    "error": "empty-stdout",
                    "stderr_tail": err[-500:],
                    "exit": proc.returncode,
                }
            )
        )
        return 2

    if proc.returncode in (0, 1, 2):
        return int(proc.returncode)
    return 2


if __name__ == "__main__":
    sys.exit(main())
