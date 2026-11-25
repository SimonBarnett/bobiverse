#!/usr/bin/env python3
"""FR #9871: cmd-trace stall while GIT/stdout announce continues.

Fail-when: cmd-trace.log age exceeds BOB_CMD_TRACE_STALL_S (default 120s) while
NSSM stdout.log stays fresh (GIT announce path alive). Distinct from FR #9900
(both logs stale / progress_ok). Heal: write stall fingerprint under chair home
and prefer shop-wire assign path when available (FR #9878). Live ircJeeves
recycle / SAMODE proof remains require_machine=walrus.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

from _common import EXIT_FINDING, EXIT_OK, non_chair_overlay, resolve_homes, run_check

BOBCALLBACK_PORT = 7700


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "common" / "scripts"


def _load_clf():
    root = str(_scripts_dir())
    if root not in sys.path:
        sys.path.insert(0, root)
    import chair_log_freshness as clf  # noqa: WPS433

    return clf


def _service_state(name: str) -> str:
    if sys.platform != "win32":
        return "skipped"
    try:
        import subprocess

        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status",
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


def heal_stall(chair: Path, snap: dict[str, Any]) -> dict[str, Any]:
    """Write fingerprint; attempt shop-wire import when present (FR #9878)."""
    clf = _load_clf()
    stamp = clf.write_stall_fingerprint(chair, snap)
    out: dict[str, Any] = {
        "attempted": True,
        "stamp": str(stamp),
        "fingerprint": snap.get("fingerprint") or clf.STALL_FINGERPRINT,
        "shop_wire": None,
        "chair_recycle": "require_machine=walrus",
    }
    try:
        import shop_wire_assign as swa  # type: ignore

        out["shop_wire"] = {
            "available": True,
            "prefer_on_mute": True,
            "cmd_trace_mute": swa.cmd_trace_mute_snapshot(chair),
        }
    except Exception as e:
        out["shop_wire"] = {"available": False, "error": type(e).__name__}
    return out


def check(args):
    chair, digest = resolve_homes(args)
    findings: list[str] = []
    notes: list[str] = []
    clf = _load_clf()
    snap = clf.cmd_trace_stall_snapshot(chair)
    svc = _service_state("ircJeeves")
    listen = _port_listening(BOBCALLBACK_PORT)
    chair_up = svc.lower() == "running" or listen

    if not chair_up:
        notes.append(
            f"soft-ok chair not local (ircJeeves={svc} listen:{BOBCALLBACK_PORT}={listen}); FR #8579"
        )
        overlay = non_chair_overlay(chair, digest, require_missing_queue=False)
        payload = {
            "ok": True,
            "skipped": "chair_not_local",
            "services": {"ircJeeves": svc},
            "stalled": False,
            "stall": snap,
            "findings": [],
            "notes": notes,
            "marker": "fr9871_cmd_trace_stall",
            "require_machine_live": "walrus",
        }
        if overlay:
            payload.update(overlay)
        return payload, EXIT_OK

    heal = None
    do_heal = not bool(getattr(args, "no_heal", False))
    if snap.get("stalled"):
        findings.append(
            "FR #9871 cmd-trace stall: cmd-trace frozen while stdout/GIT announce fresh "
            f"(cmd_trace_age_s={snap.get('cmd_trace_age_s')} stdout_age_s={snap.get('stdout_age_s')} "
            f"max={snap.get('max_age_s')}; fingerprint={snap.get('fingerprint')}; "
            "heal=shop_wire_or_chair_recycle require_machine=walrus for live recycle)"
        )
        if do_heal:
            try:
                heal = heal_stall(chair, snap)
                notes.append(f"heal stamp={heal.get('stamp')}")
            except Exception as e:
                heal = {"attempted": True, "error": f"{type(e).__name__}:{e}"}
                notes.append(f"heal error: {heal['error']}")

    ok = not findings
    return (
        {
            "ok": ok,
            "services": {"ircJeeves": svc},
            "stalled": bool(snap.get("stalled")),
            "stall": snap,
            "heal": heal,
            "findings": findings,
            "notes": notes,
            "marker": "fr9871_cmd_trace_stall",
            "require_machine_live": "walrus",
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    # Optional --no-heal for report-only.
    argv = list(sys.argv[1:] if argv is None else argv)
    no_heal = False
    filtered = []
    for a in argv:
        if a == "--no-heal":
            no_heal = True
        else:
            filtered.append(a)

    def _check(args):
        args.no_heal = no_heal
        return check(args)

    return run_check(
        "cmd_trace_stall",
        "cmd-trace stall while GIT/stdout fresh (FR #9871; exit 0/1/2)",
        _check,
        filtered,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
