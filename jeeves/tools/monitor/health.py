#!/usr/bin/env python3
"""Health check: ircJeeves service, local chair logs, webhook probe stamp (token-free)."""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check

BOBCALLBACK_PORT = 7700


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


def _service_start_type(name: str) -> str:
    """Return Automatic/Manual/Disabled/missing/skipped (FR #6587)."""
    if sys.platform != "win32":
        return "skipped"
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).StartType",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        s = (r.stdout or "").strip()
        return s or "missing"
    except Exception as e:
        return f"error:{type(e).__name__}"


def _bobircd_expected_running(start_type: str) -> bool:
    """Local Ergo hosts expect BobIrcd Running; Disabled means remote Ergo by design (FR #6587)."""
    st = (start_type or "").strip().lower()
    if st in ("disabled", "skipped"):
        return False
    return True


def _scheduled_task_state(name: str) -> str:
    """FR #1043: BobCallback on ionos is a Scheduled Task, not Get-Service."""
    if sys.platform != "win32":
        return "skipped"
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).State",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        s = (r.stdout or "").strip()
        return s or "missing"
    except Exception as e:
        return f"error:{type(e).__name__}"


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _bobcallback_ok() -> tuple[str, bool]:
    """Healthy only when :7700 listens (or skipped). Task Ready/Running alone is a false ok (FR #1767)."""
    st = _service_state("BobCallback")
    if st.lower() == "skipped":
        return st, True
    if _port_listening(BOBCALLBACK_PORT):
        return f"listen:{BOBCALLBACK_PORT}", True
    task = _scheduled_task_state("BobCallback")
    # Ready/Running without LISTEN = wedge / multi-supervisor lock fight — report finding.
    if task.lower() in ("running", "ready"):
        return f"task:{task}-no-listen", False
    if st.lower() == "running":
        return f"{st}-no-listen", False
    return st if st != "missing" else f"missing/task:{task}", False


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    notes = []
    services = {}
    for svc in ("ircJeeves", "BobIrcd"):
        st = _service_state(svc)
        start = _service_start_type(svc)
        if svc == "BobIrcd":
            # FR #6587: Stopped+Disabled (remote Ergo) is intentional — soft note only.
            # Never restart BobIrcd from heal; do not fail self-test/heal for that design.
            if st.lower() not in ("running", "skipped"):
                if _bobircd_expected_running(start):
                    services[svc] = st
                    findings.append(f"service {svc}={st}")
                else:
                    label = f"{st}/{start}" if start and start.lower() != "missing" else st
                    services[svc] = label
                    notes.append(
                        f"BobIrcd={label} soft-ok (StartType=Disabled or skipped; "
                        f"remote Ergo / never restart from heal; FR #6587)"
                    )
            else:
                services[svc] = st
        else:
            services[svc] = st
            if st.lower() not in ("running", "skipped"):
                findings.append(f"service {svc}={st}")
    bc_label, bc_ok = _bobcallback_ok()
    services["BobCallback"] = bc_label
    if not bc_ok:
        findings.append(
            f"BobCallback={bc_label} (expect Get-Service Running, Scheduled Task Running, or :{BOBCALLBACK_PORT} listen)"
        )
    if services.get("ircJeeves", "").lower() == "running" and not chair.is_dir():
        findings.append(f"chair home missing: {chair}")
    ok = not findings
    return (
        {
            "ok": ok,
            "services": services,
            "chair_home": str(chair),
            "findings": findings,
            "notes": notes,
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
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
