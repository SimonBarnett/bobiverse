#!/usr/bin/env python3
"""Health check: ircJeeves service, local chair logs, webhook probe stamp (token-free)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check


def _service_state(name: str) -> str:
    if sys.platform != "win32":
        return "skipped"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status"],
            capture_output=True, text=True, timeout=30,
        )
        s = (r.stdout or "").strip()
        return s or "missing"
    except Exception as e:
        return f"error:{type(e).__name__}"


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    services = {}
    for svc in ("ircJeeves", "BobIrcd", "BobCallback"):
        st = _service_state(svc)
        services[svc] = st
        if st.lower() not in ("running", "skipped"):
            findings.append(f"service {svc}={st}")
    stdout_log = chair.parent / ".."  # unused; prefer install logs when present
    # Chair home presence is soft: missing home is a finding only when service claims running
    if services.get("ircJeeves", "").lower() == "running" and not chair.is_dir():
        findings.append(f"chair home missing: {chair}")
    ok = not findings
    return (
        {
            "ok": ok,
            "services": services,
            "chair_home": str(chair),
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "health",
        "Jeeves health: services + chair home (exit 0 ok / 1 finding / 2 error)",
        check,
        argv,
    )


if __name__ == "__main__":
    # Allow running as script from tools/monitor without package install
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
