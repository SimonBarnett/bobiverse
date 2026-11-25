#!/usr/bin/env python3
"""FR #9826 / #9836: when ircJeeves is intended-up, /bob/v1/report must serve HTTP 200.

CAST IRON: Jeeves on IRC implies webhooks up. Detect chair-up + report-down,
or chair-Stopped (Automatic) while Ergo up; optionally heal by starting ircJeeves
+ BobCallback (never Ergo/BobIrcd), re-probe local :7700 and public report, EXIT 1
if still down.
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

from _common import EXIT_FINDING, EXIT_OK, live_report_url, non_chair_overlay, resolve_homes, run_check

BOBCALLBACK_PORT = 7700
DEFAULT_LOCAL_REPORT = "http://127.0.0.1:7700/bob/v1/report"


def auto_heal_enabled(env: Optional[dict] = None) -> bool:
    env = os.environ if env is None else env
    raw = (env.get("BOB_WEBHOOKS_UP_AUTO") or env.get("BOB_HEALTH_AUTO") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_report_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    return (env.get("BOB_WEBHOOKS_LOCAL_REPORT_URL") or DEFAULT_LOCAL_REPORT).strip()


def public_report_url(env: Optional[dict] = None) -> str:
    return live_report_url(env)


def chair_intended_up(start_type: str) -> bool:
    st = (start_type or "").strip().lower()
    return st in ("automatic", "automaticdelayedstart")


def ergo_is_up(bobircd_state: str, bobircd_start: str) -> bool:
    st = (bobircd_state or "").strip().lower()
    if st in ("running", "skipped"):
        return True
    bst = (bobircd_start or "").strip().lower()
    if bst in ("disabled", "skipped"):
        return True
    return False


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


def _service_start_type(name: str) -> str:
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


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _probe_http_report(
    url: str,
    *,
    timeout_s: float = 10.0,
    ua: str = "BobiverseJeevesMonitor-webhooks_up_with_chair/1.0",
) -> tuple[bool, int, str]:
    target = (url or "").strip()
    if not target:
        return False, 0, "empty_url"
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={"User-Agent": ua, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            code = int(getattr(resp, "status", None) or resp.getcode() or 0)
            return code == 200, code, f"status={code}"
    except urllib.error.HTTPError as exc:
        return False, int(exc.code or 0), f"http={exc.code}"
    except Exception as exc:
        return False, 0, f"{type(exc).__name__}:{exc}"


def probe_local_report(
    url: Optional[str] = None,
    *,
    timeout_s: float = 10.0,
) -> tuple[bool, int, str]:
    """Return (ok, status_or_0, detail). ok means HTTP 200."""
    return _probe_http_report(url or local_report_url(), timeout_s=timeout_s)


def probe_public_report(
    url: Optional[str] = None,
    *,
    timeout_s: float = 12.0,
) -> tuple[bool, int, str]:
    return _probe_http_report(
        url or public_report_url(),
        timeout_s=timeout_s,
        ua="BobiverseJeevesMonitor-webhooks_up_public/1.0",
    )


def heal_start_ircjeeves() -> dict[str, Any]:
    """Start ircJeeves when Stopped. Never touches Ergo or BobIrcd (FR #9836)."""
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
                    "$s=Get-Service -Name 'ircJeeves' -ErrorAction SilentlyContinue; "
                    "if (-not $s) { 'missing' } "
                    "elseif ($s.Status -eq 'Running') { 'already_running' } "
                    "else { Start-Service ircJeeves -ErrorAction SilentlyContinue; "
                    "  Start-Sleep -Seconds 2; "
                    "  if ((Get-Service ircJeeves -ErrorAction SilentlyContinue).Status -eq 'Running') { "
                    "    'service_start' } else { 'service_start_failed' } }"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (r.stdout or "").strip()
        if out:
            actions.append(out.splitlines()[-1].strip())
        ok = bool(actions) and actions[-1] in ("service_start", "already_running")
        return {"ok": ok, "actions": actions, "rc": r.returncode}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}", "actions": actions}


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
    irc_start = _service_start_type("ircJeeves")
    bobircd = _service_state("BobIrcd")
    bobircd_start = _service_start_type("BobIrcd")
    url = local_report_url()
    pub_url = public_report_url()
    listening = _port_listening(BOBCALLBACK_PORT)
    ok_probe, status, detail = probe_local_report(url)
    pub_ok, pub_status, pub_detail = probe_public_report(pub_url)
    heal: dict[str, Any] = {}
    findings: list[str] = []
    notes: list[str] = []

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
                "public_report_url": pub_url,
                "public_report_ok": pub_ok,
                "port_listening": listening,
                "findings": [],
            },
            EXIT_OK,
        )

    intended = chair_intended_up(irc_start)
    ergo_up = ergo_is_up(bobircd, bobircd_start)
    chair_up = irc.lower() == "running"

    # FR #9826: Running + local down
    if chair_up and not ok_probe:
        findings.append(
            f"CAST IRON FR #9826: ircJeeves Running but local report not 200 "
            f"({detail}; listen={listening}; url={url})"
        )
    # FR #9836: Running + public down (fail-when EXIT 0)
    if chair_up and not pub_ok:
        findings.append(
            f"CAST IRON FR #9836: ircJeeves Running but public report not 200 "
            f"({pub_detail}; url={pub_url})"
        )
    # FR #9836: Stopped + intended-up + Ergo up
    if (not chair_up) and intended and ergo_up:
        findings.append(
            f"CAST IRON FR #9836: ircJeeves={irc} (intended-up StartType={irc_start}) "
            f"while Ergo up; public={pub_detail}"
        )

    if findings and auto_heal_enabled() and not getattr(args, "dry_run", False):
        if (not chair_up) and intended and ergo_up:
            heal["ircjeeves"] = heal_start_ircjeeves()
        heal["bobcallback"] = heal_bobcallback_local()
        try:
            import time

            time.sleep(2.0)
        except Exception:
            pass
        irc = _service_state("ircJeeves")
        chair_up = irc.lower() == "running"
        ok_probe, status, detail = probe_local_report(url)
        pub_ok, pub_status, pub_detail = probe_public_report(pub_url)
        listening = _port_listening(BOBCALLBACK_PORT)
        if chair_up and ok_probe and pub_ok:
            findings = []
            notes.append(
                "FR #9836 heal restored ircJeeves + local/public /bob/v1/report HTTP 200"
            )
        elif findings:
            # refresh finding text after heal attempt
            findings = []
            if chair_up and not ok_probe:
                findings.append(
                    f"CAST IRON FR #9826: ircJeeves Running but local report not 200 "
                    f"({detail}; listen={listening}; url={url})"
                )
            if chair_up and not pub_ok:
                findings.append(
                    f"CAST IRON FR #9836: ircJeeves Running but public report not 200 "
                    f"({pub_detail}; url={pub_url})"
                )
            if (not chair_up) and intended and ergo_up:
                findings.append(
                    f"CAST IRON FR #9836: ircJeeves={irc} still down after heal "
                    f"(StartType={irc_start}); public={pub_detail}"
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
                "public_report_url": pub_url,
                "public_report_ok": pub_ok,
                "public_report_status": pub_status,
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
            "ircJeeves_start_type": irc_start,
            "local_report_url": url,
            "local_report_ok": ok_probe,
            "local_report_status": status,
            "local_report_detail": detail,
            "public_report_url": pub_url,
            "public_report_ok": pub_ok,
            "public_report_status": pub_status,
            "public_report_detail": pub_detail,
            "port_listening": listening,
            "heal": heal,
            "findings": findings,
            "notes": notes,
            "chair_home": str(chair),
            "remediation": (
                "Start-Service ircJeeves; Start-Jeeves / BobCallback / schtasks BobCallback; "
                "optional Start-Service W3SVC; never Ergo/BobIrcd (FR #9836 / #9826)"
                if findings
                else ""
            ),
            "fr_hint": "CAST IRON Jeeves on IRC => webhooks up (FR #9826 / #9836)",
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv: Optional[list[str]] = None) -> int:
    return run_check(
        "webhooks_up_with_chair",
        "CAST IRON FR #9826/#9836: intended-up ircJeeves requires local+public /bob/v1/report HTTP 200",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
