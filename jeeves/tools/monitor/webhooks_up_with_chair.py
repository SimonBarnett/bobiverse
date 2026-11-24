#!/usr/bin/env python3
"""FR #9826: when ircJeeves is Running, local /bob/v1/report must serve HTTP 200.

CAST IRON: Jeeves on IRC implies webhooks up. Detect chair-up + report-down,
optionally heal BobCallback (never Ergo/BobIrcd), re-probe, EXIT 1 if still down.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from _common import EXIT_FINDING, EXIT_OK, non_chair_overlay, resolve_homes, run_check

BOBCALLBACK_PORT = 7700
DEFAULT_LOCAL_REPORT = "http://127.0.0.1:7700/bob/v1/report"


def auto_heal_enabled(env: Optional[dict] = None) -> bool:
    env = os.environ if env is None else env
    raw = (env.get("BOB_WEBHOOKS_UP_AUTO") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_report_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    return (env.get("BOB_WEBHOOKS_LOCAL_REPORT_URL") or DEFAULT_LOCAL_REPORT).strip()


def _service_state(name: str) -> str:
    if sys.platform != "win32":
        return "skipped"
    try:
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


def probe_local_report(
    url: Optional[str] = None,
    *,
    timeout_s: float = 10.0,
) -> tuple[bool, int, str]:
    """Return (ok, status_or_0, detail). ok means HTTP 200."""
    target = (url or DEFAULT_LOCAL_REPORT).strip()
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={"User-Agent": "BobiverseJeevesMonitor-webhooks_up_with_chair/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            code = int(getattr(resp, "status", None) or resp.getcode() or 0)
            return code == 200, code, f"status={code}"
    except urllib.error.HTTPError as exc:
        return False, int(exc.code or 0), f"http={exc.code}"
    except Exception as exc:
        return False, 0, f"{type(exc).__name__}:{exc}"


def heal_bobcallback_local() -> dict[str, Any]:
    """Best-effort BobCallback / :7700 heal. Never touches Ergo or BobIrcd."""
    if sys.platform != "win32":
        return {"ok": False, "skipped": "non_win32"}
    actions: list[str] = []
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$ErrorActionPreference='Continue'; "
                    "$t=Get-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue; "
                    "if ($t) { "
                    "  if ($t.State -eq 'Running') { Stop-ScheduledTask -TaskName 'BobCallback' -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1 }; "
                    "  Start-ScheduledTask -TaskName 'BobCallback'; "
                    "  'schtasks_start' "
                    "} else { "
                    "  $svc=Get-Service -Name 'BobCallback' -ErrorAction SilentlyContinue; "
                    "  if ($svc -and $svc.Status -ne 'Running') { Start-Service BobCallback; 'service_start' } "
                    "  elseif ($svc) { Restart-Service BobCallback -Force -ErrorAction SilentlyContinue; 'service_restart' } "
                    "  else { 'no_task_or_service' } "
                    "}"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (r.stdout or "").strip()
        if out:
            actions.append(out.splitlines()[-1].strip())
        # Soft IIS front-door heal when W3SVC exists (public ARR); never BobIrcd.
        r2 = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$s=Get-Service -Name 'W3SVC' -ErrorAction SilentlyContinue; "
                    "if (-not $s) { 'w3svc_absent' } "
                    "elseif ($s.Status -eq 'Running') { 'w3svc_running' } "
                    "else { Start-Service W3SVC -ErrorAction SilentlyContinue; "
                    "  if ((Get-Service W3SVC -ErrorAction SilentlyContinue).Status -eq 'Running') { 'w3svc_started' } else { 'w3svc_start_failed' } }"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        w = (r2.stdout or "").strip()
        if w:
            actions.append(w.splitlines()[-1].strip())
        return {"ok": True, "actions": actions, "rc": r.returncode}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}", "actions": actions}


def check(args: Any) -> tuple[dict[str, Any], int]:
    chair, digest = resolve_homes(args)
    irc = _service_state("ircJeeves")
    url = local_report_url()
    listening = _port_listening(BOBCALLBACK_PORT)
    ok_probe, status, detail = probe_local_report(url)
    heal: dict[str, Any] = {}
    findings: list[str] = []
    notes: list[str] = []

    chair_up = irc.lower() == "running"
    if irc.lower() == "skipped":
        # Non-Windows / CI: soft ok.
        return (
            {
                "ok": True,
                "soft_ok": True,
                "reason": "ircJeeves_skipped",
                "ircJeeves": irc,
                "local_report_url": url,
                "local_report_ok": ok_probe,
                "port_listening": listening,
                "findings": [],
            },
            EXIT_OK,
        )

    if chair_up and not ok_probe:
        if auto_heal_enabled() and not getattr(args, "dry_run", False):
            heal = heal_bobcallback_local()
            # brief settle then re-probe
            try:
                import time

                time.sleep(2.0)
            except Exception:
                pass
            ok_probe, status, detail = probe_local_report(url)
            listening = _port_listening(BOBCALLBACK_PORT)
        if not ok_probe:
            findings.append(
                f"CAST IRON FR #9826: ircJeeves Running but local report not 200 "
                f"({detail}; listen={listening}; url={url})"
            )

    if findings:
        overlay = non_chair_overlay(chair, digest, require_missing_queue=True)
        if overlay:
            for f in findings:
                notes.append(f"non-chair soft-ok (live /report fresh): {f}")
            findings = []
            notes.append(
                "FR #8579 non-chair overlay: local ircJeeves/BobCallback are not the live chair"
            )
            payload = {
                "ok": True,
                "soft_ok": True,
                "ircJeeves": irc,
                "local_report_url": url,
                "local_report_ok": ok_probe,
                "local_report_status": status,
                "port_listening": listening,
                "heal": heal,
                "findings": [],
                "notes": notes,
            }
            payload.update(overlay)
            return payload, EXIT_OK

    ok = not findings
    return (
        {
            "ok": ok,
            "ircJeeves": irc,
            "local_report_url": url,
            "local_report_ok": ok_probe,
            "local_report_status": status,
            "local_report_detail": detail,
            "port_listening": listening,
            "heal": heal,
            "findings": findings,
            "notes": notes,
            "chair_home": str(chair),
            "remediation": (
                "Start-Jeeves / BobCallback / schtasks BobCallback; "
                "optional Start-Service W3SVC; never Ergo/BobIrcd (FR #9826)"
                if findings
                else ""
            ),
            "fr_hint": "CAST IRON Jeeves on IRC => webhooks up (FR #9826)",
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv: Optional[list[str]] = None) -> int:
    return run_check(
        "webhooks_up_with_chair",
        "CAST IRON FR #9826: ircJeeves Running requires local /bob/v1/report HTTP 200",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
