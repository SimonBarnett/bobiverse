#!/usr/bin/env python3
"""Health check: ircJeeves service, local chair logs, webhook probe stamp (token-free).

FR #9836: when ircJeeves is Stopped (intended-up) or public /bob/v1/report is 502/timeout
while Ergo is up, EXIT 1 and optionally heal (start chair + BobCallback/W3SVC), then
re-probe local :7700 and public report before returning OK. Never touch Ergo/BobIrcd.

FR #9864: digest-ok XOR report-fail => EXIT 1 + fingerprint ``webhook:digest_ok_report_hang``.
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

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    live_report_url,
    non_chair_overlay,
    resolve_homes,
    run_check,
)

BOBCALLBACK_PORT = 7700
DEFAULT_LOCAL_REPORT = "http://127.0.0.1:7700/bob/v1/report"
DEFAULT_LOCAL_DIGEST = "http://127.0.0.1:7700/bob/v1/digest"
DIGEST_OK_REPORT_HANG_FP = "webhook:digest_ok_report_hang"


def auto_heal_enabled(env: Optional[dict] = None) -> bool:
    env = os.environ if env is None else env
    raw = (env.get("BOB_HEALTH_AUTO") or env.get("BOB_WEBHOOKS_UP_AUTO") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def local_report_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    return (env.get("BOB_WEBHOOKS_LOCAL_REPORT_URL") or DEFAULT_LOCAL_REPORT).strip()


def public_report_url(env: Optional[dict] = None) -> str:
    return live_report_url(env)


def _report_to_digest_url(report_url: str) -> str:
    u = (report_url or "").rstrip("/")
    if u.endswith("/bob/v1/report"):
        return u[: -len("/bob/v1/report")] + "/bob/v1/digest"
    if u.endswith("/report"):
        return u[: -len("/report")] + "/digest"
    return DEFAULT_LOCAL_DIGEST


def local_digest_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    override = (env.get("BOB_WEBHOOKS_LOCAL_DIGEST_URL") or "").strip()
    if override:
        return override
    return _report_to_digest_url(local_report_url(env))


def public_digest_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    override = (env.get("BOB_WEBHOOKS_PUBLIC_DIGEST_URL") or "").strip()
    if override:
        return override
    return _report_to_digest_url(public_report_url(env))


def chair_intended_up(start_type: str) -> bool:
    """Automatic (+ delayed) means the chair is supposed to be Running (FR #9836)."""
    st = (start_type or "").strip().lower()
    return st in ("automatic", "automaticdelayedstart")


def ergo_is_up(bobircd_state: str, bobircd_start: str) -> bool:
    """True when local BobIrcd is Running, or remote-Ergo (Disabled) is assumed up."""
    st = (bobircd_state or "").strip().lower()
    if st in ("running", "skipped"):
        return True
    # FR #6587: Stopped+Disabled = remote Ergo by design; treat Ergo as up for chair heal.
    if not _bobircd_expected_running(bobircd_start):
        return True
    return False


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
    # Ready/Running without LISTEN = wedge / multi-supervisor lock fight - report finding.
    if task.lower() in ("running", "ready"):
        return f"task:{task}-no-listen", False
    if st.lower() == "running":
        return f"{st}-no-listen", False
    return st if st != "missing" else f"missing/task:{task}", False


def _probe_http_report(
    url: str,
    *,
    timeout_s: float = 10.0,
    ua: str = "BobiverseJeevesMonitor-health/1.0",
) -> tuple[bool, int, str]:
    """Return (ok, status_or_0, detail). ok means HTTP 200."""
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
    return _probe_http_report(
        url or local_report_url(),
        timeout_s=timeout_s,
        ua="BobiverseJeevesMonitor-health-local/1.0",
    )


def probe_public_report(
    url: Optional[str] = None,
    *,
    timeout_s: float = 12.0,
) -> tuple[bool, int, str]:
    return _probe_http_report(
        url or public_report_url(),
        timeout_s=timeout_s,
        ua="BobiverseJeevesMonitor-health-public/1.0",
    )


def probe_local_digest(
    url: Optional[str] = None,
    *,
    timeout_s: float = 6.0,
) -> tuple[bool, int, str]:
    return _probe_http_report(
        url or local_digest_url(),
        timeout_s=timeout_s,
        ua="BobiverseJeevesMonitor-health-digest/1.0",
    )


def probe_public_digest(
    url: Optional[str] = None,
    *,
    timeout_s: float = 8.0,
) -> tuple[bool, int, str]:
    return _probe_http_report(
        url or public_digest_url(),
        timeout_s=timeout_s,
        ua="BobiverseJeevesMonitor-health-digest-public/1.0",
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
    """Best-effort BobCallback / :7700 + soft W3SVC heal. Never touches Ergo or BobIrcd."""
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


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    notes = []
    overlay = None
    heal: dict[str, Any] = {}
    services = {}
    irc_start = "missing"
    bobircd_start = "missing"
    for svc in ("ircJeeves", "BobIrcd"):
        st = _service_state(svc)
        start = _service_start_type(svc)
        if svc == "ircJeeves":
            irc_start = start
        if svc == "BobIrcd":
            bobircd_start = start
            # FR #6587: Stopped+Disabled (remote Ergo) is intentional - soft note only.
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

    local_url = local_report_url()
    public_url = public_report_url()
    local_dig_url = local_digest_url()
    public_dig_url = public_digest_url()
    local_ok, local_status, local_detail = probe_local_report(local_url)
    public_ok, public_status, public_detail = probe_public_report(public_url)
    local_dig_ok, local_dig_status, local_dig_detail = probe_local_digest(local_dig_url)
    public_dig_ok, public_dig_status, public_dig_detail = probe_public_digest(public_dig_url)
    irc_state = str(services.get("ircJeeves") or "")
    bobircd_state = str(services.get("BobIrcd") or "")
    intended = chair_intended_up(irc_start)
    ergo_up = ergo_is_up(bobircd_state, bobircd_start)
    chair_up = irc_state.lower() == "running"
    webhooks_up = bool(local_ok and public_ok)
    fingerprint = ""

    # FR #9836: intended-up disagreeing with webhooks (public or local down) while Ergo up.
    if ergo_up and irc_state.lower() != "skipped":
        if intended and chair_up and not public_ok:
            findings.append(
                f"CAST IRON FR #9836: ircJeeves Running but public report not 200 "
                f"({public_detail}; url={public_url})"
            )
        if intended and chair_up and not local_ok:
            findings.append(
                f"CAST IRON FR #9836: ircJeeves Running but local report not 200 "
                f"({local_detail}; url={local_url})"
            )
        if intended and (not chair_up) and ergo_up:
            # service finding already present; pin CAST IRON cue for heal.
            if not any("9836" in f for f in findings):
                findings.append(
                    f"CAST IRON FR #9836: ircJeeves={irc_state} (intended-up StartType={irc_start}) "
                    f"while Ergo up; public={public_detail}"
                )

    # FR #9864: digest-ok XOR report-fail.
    xor_local = bool(local_dig_ok and not local_ok)
    xor_public = bool(public_dig_ok and not public_ok)
    if chair_up and (xor_local or xor_public):
        fingerprint = DIGEST_OK_REPORT_HANG_FP
        findings.append(
            f"CAST IRON FR #9864: digest ok but report hang/fail "
            f"(local digest={local_dig_detail} report={local_detail}; "
            f"public digest={public_dig_detail} report={public_detail}; "
            f"fingerprint={DIGEST_OK_REPORT_HANG_FP})"
        )

    # Same-turn heal: start chair when Stopped+intended+Ergo-up; restore webhooks; re-probe both.
    need_heal = bool(findings) and auto_heal_enabled() and not getattr(args, "dry_run", False)
    if need_heal and ergo_up and intended and irc_state.lower() != "skipped":
        if not chair_up:
            heal["ircjeeves"] = heal_start_ircjeeves()
        if not webhooks_up or not bc_ok or fingerprint:
            heal["bobcallback"] = heal_bobcallback_local()
        try:
            import time

            time.sleep(2.0)
        except Exception:
            pass
        # Refresh service + probes after heal.
        irc_state = _service_state("ircJeeves")
        services["ircJeeves"] = irc_state
        bc_label, bc_ok = _bobcallback_ok()
        services["BobCallback"] = bc_label
        local_ok, local_status, local_detail = probe_local_report(local_url)
        public_ok, public_status, public_detail = probe_public_report(public_url)
        local_dig_ok, local_dig_status, local_dig_detail = probe_local_digest(local_dig_url)
        public_dig_ok, public_dig_status, public_dig_detail = probe_public_digest(public_dig_url)
        chair_up = irc_state.lower() == "running"
        webhooks_up = bool(local_ok and public_ok)
        if chair_up and webhooks_up and bc_ok:
            findings = [
                f
                for f in findings
                if not (
                    "ircJeeves" in f
                    or "BobCallback" in f
                    or "9836" in f
                    or "9826" in f
                    or "9864" in f
                    or "public report" in f
                    or "local report" in f
                )
            ]
            fingerprint = ""
            notes.append(
                "FR #9836 heal restored ircJeeves + local/public /bob/v1/report HTTP 200"
            )
        else:
            xor_local = bool(local_dig_ok and not local_ok)
            xor_public = bool(public_dig_ok and not public_ok)
            if chair_up and (xor_local or xor_public):
                fingerprint = DIGEST_OK_REPORT_HANG_FP
                if not any("9864" in f for f in findings):
                    findings.append(
                        f"CAST IRON FR #9864: digest ok but report hang/fail after heal "
                        f"(fingerprint={DIGEST_OK_REPORT_HANG_FP})"
                    )

    if findings:
        # FR #8579: local chair services absent on a worker/monitor host while the
        # live ionos chair reports fresh via /bob/v1/report - soft-pass, do not
        # file false ionos outage cues.
        overlay = non_chair_overlay(chair, _digest, require_missing_queue=True)
        if overlay:
            for f in findings:
                notes.append(f"non-chair soft-ok (live /report fresh): {f}")
            notes.append(
                "FR #8579 non-chair overlay: local services/chair files are not the "
                f"live chair; live ts={overlay.get('live_report_ts')} "
                f"chairNick={overlay.get('live_chair_nick')}"
            )
            findings = []
            fingerprint = ""
    ok = not findings
    payload = {
        "ok": ok,
        "services": services,
        "chair_home": str(chair),
        "findings": findings,
        "notes": notes,
        "local_report_url": local_url,
        "local_report_ok": local_ok,
        "local_report_status": local_status,
        "local_report_detail": local_detail,
        "public_report_url": public_url,
        "public_report_ok": public_ok,
        "public_report_status": public_status,
        "public_report_detail": public_detail,
        "local_digest_url": local_dig_url,
        "local_digest_ok": local_dig_ok,
        "local_digest_status": local_dig_status,
        "local_digest_detail": local_dig_detail,
        "public_digest_url": public_dig_url,
        "public_digest_ok": public_dig_ok,
        "public_digest_status": public_dig_status,
        "public_digest_detail": public_dig_detail,
        "chair_intended_up": intended,
        "ergo_up": ergo_up,
        "heal": heal,
        "remediation": (
            "Start-Service ircJeeves; Start-Jeeves / BobCallback / schtasks BobCallback; "
            "optional Start-Service W3SVC; probe local :7700 and public report; "
            "never Ergo/BobIrcd (FR #9836 / #9826 / #9864)"
            if findings
            else ""
        ),
        "fr_hint": "CAST IRON chair heal + public report (FR #9836 / #9864)",
    }
    if fingerprint:
        payload["fingerprint"] = fingerprint
        payload["fingerprints"] = [fingerprint]
    if overlay:
        payload.update(overlay)
    return (payload, EXIT_OK if ok else EXIT_FINDING)


def main(argv=None) -> int:
    return run_check(
        "health",
        "Jeeves health: services + chair home + local/public report (exit 0 ok / 1 finding / 2 error)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
