#!/usr/bin/env python3
"""FR #9900: chair log freshness vs HTTP /health ok (stdout stale class).

Fail-when: local /health reports ok=true while NSSM stdout.log and/or
cmd-trace.log are older than BOB_CHAIR_PROGRESS_MAX_AGE_S (default 30m).
Digest last_digest_write freshness does not excuse stale AppStdout.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from _common import EXIT_FINDING, EXIT_OK, non_chair_overlay, resolve_homes, run_check

BOBCALLBACK_PORT = 7700
DEFAULT_HEALTH = "http://127.0.0.1:7700/health"


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "common" / "scripts"


def _load_chair_log_freshness():
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


def probe_local_health(
    url: str | None = None,
    *,
    timeout_s: float = 5.0,
) -> tuple[bool, dict[str, Any]]:
    """Return (http_ok, body_dict_or_empty). http_ok means HTTP 200."""
    target = (url or os.environ.get("BOB_CHAIR_HEALTH_URL") or DEFAULT_HEALTH).strip()
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={"User-Agent": "BobiverseJeevesMonitor-chair_progress/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            code = int(getattr(resp, "status", None) or resp.getcode() or 0)
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                doc = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                doc = {}
            if not isinstance(doc, dict):
                doc = {}
            return code == 200, doc
    except urllib.error.HTTPError as exc:
        body: dict[str, Any] = {}
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            if isinstance(parsed, dict):
                body = parsed
        except Exception:
            pass
        return False, body
    except Exception as exc:
        return False, {"progress_reason": f"probe_error:{type(exc).__name__}:{exc}"}


def check(args):
    chair, digest = resolve_homes(args)
    findings: list[str] = []
    notes: list[str] = []
    clf = _load_chair_log_freshness()
    snap = clf.progress_snapshot(chair)
    svc = _service_state("ircJeeves")
    listen = _port_listening(BOBCALLBACK_PORT)
    health_http_ok, health_doc = probe_local_health()
    health_ok = bool(health_doc.get("ok")) if "ok" in health_doc else health_http_ok

    # Prefer /health progress fields when present; else local snapshot.
    if health_doc.get("progress_ok") is not None:
        progress_ok = bool(health_doc.get("progress_ok"))
        reason = str(health_doc.get("progress_reason") or snap.get("progress_reason") or "")
        stdout_age = health_doc.get("stdout_age_s", snap.get("stdout_age_s"))
        cmd_age = health_doc.get("cmd_trace_age_s", snap.get("cmd_trace_age_s"))
        max_age = health_doc.get("progress_max_age_s", snap.get("progress_max_age_s"))
    else:
        progress_ok = bool(snap.get("progress_ok"))
        reason = str(snap.get("progress_reason") or "")
        stdout_age = snap.get("stdout_age_s")
        cmd_age = snap.get("cmd_trace_age_s")
        max_age = snap.get("progress_max_age_s")

    chair_up = svc.lower() == "running" or listen or health_http_ok
    if not chair_up:
        notes.append(
            f"soft-ok chair not local (ircJeeves={svc} listen:{BOBCALLBACK_PORT}={listen} "
            f"health_http={health_http_ok}); FR #8579"
        )
        overlay = non_chair_overlay(chair, digest, require_missing_queue=False)
        payload = {
            "ok": True,
            "skipped": "chair_not_local",
            "services": {"ircJeeves": svc},
            "health_http_ok": health_http_ok,
            "health_ok": health_ok,
            "progress_ok": progress_ok,
            "progress_reason": reason,
            "stdout_age_s": stdout_age,
            "cmd_trace_age_s": cmd_age,
            "progress_max_age_s": max_age,
            "findings": [],
            "notes": notes,
            "marker": "fr9900_chair_progress",
        }
        if overlay:
            payload.update(overlay)
        return payload, EXIT_OK

    # Fail-when: health green + stale logs (FR #8781 / #9900 class).
    if health_ok and not progress_ok and reason == "stale_logs":
        findings.append(
            "FR #9900 chair-progress: /health ok=true but stdout/cmd-trace stale "
            f"(stdout_age_s={stdout_age} cmd_trace_age_s={cmd_age} "
            f"max={max_age}; digest write does not prove AppStdout progress)"
        )
    elif not progress_ok and reason == "stale_logs" and chair_up:
        # Chair up but /health ok false/unknown — still surface stale logs.
        findings.append(
            "FR #9900 chair-progress: stdout/cmd-trace stale while ircJeeves/"
            f":{BOBCALLBACK_PORT} up (stdout_age_s={stdout_age} "
            f"cmd_trace_age_s={cmd_age} max={max_age})"
        )
    elif reason == "no_log_files":
        notes.append("no stdout.log / cmd-trace.log present; cannot measure progress")

    ok = not findings
    return (
        {
            "ok": ok,
            "services": {"ircJeeves": svc},
            "health_http_ok": health_http_ok,
            "health_ok": health_ok,
            "progress_ok": progress_ok,
            "progress_reason": reason,
            "stdout_age_s": stdout_age,
            "cmd_trace_age_s": cmd_age,
            "progress_max_age_s": max_age,
            "stdout_path": snap.get("stdout_path"),
            "cmd_trace_path": snap.get("cmd_trace_path"),
            "findings": findings,
            "notes": notes,
            "marker": "fr9900_chair_progress",
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "chair_progress",
        "Chair log freshness vs /health ok (FR #9900; exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
