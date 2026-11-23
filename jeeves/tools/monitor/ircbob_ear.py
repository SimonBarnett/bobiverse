#!/usr/bin/env python3
"""FR #9144: token-free ircBob ear / digest offline check + local auto-heal.

Chair path: digest machines with online=false, status \"I am offline\", or stale
lastSeen. Local path (win32): Get-Service ircBob; when Stopped, Start-Service
once and re-check (monitor auto-heal). TipForm wording for ear-offline vs
unreachable lives in Get-BobTrayHover.ps1.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check

DEFAULT_MAX_AGE_SEC = 900  # align with stale_digest
SERVICE_NAME = "ircBob"


def _parse_iso_age_s(raw: object, now: float) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1_000_000_000_000:
            ts = ts / 1000.0
        if ts > 1_000_000_000:
            return now - ts
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now - parsed.timestamp()


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


def _start_service(name: str) -> tuple[bool, str]:
    """Local Start-Service heal. Returns (ok, detail). Never touches Ergo/BobIrcd."""
    if sys.platform != "win32":
        return False, "skipped"
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Start-Service -Name '{name}' -ErrorAction Stop; "
                f"(Get-Service -Name '{name}').Status",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0 and out.lower() == "running":
            return True, out
        detail = out or err or f"exit={r.returncode}"
        return False, detail[:240]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _machine_ear_offline(ent: dict) -> bool:
    if not isinstance(ent, dict):
        return False
    if ent.get("online") is False:
        return True
    status = str(ent.get("status") or "").strip().lower()
    if "i am offline" in status or status == "offline":
        return True
    return False


def _heal_local_ear(svc: str, findings: list[str], notes: list[str]) -> tuple[str, str | None]:
    """If local ircBob is installed and not Running, Start-Service once.

    Returns (status_after, heal_result) where heal_result is
    'started'|'failed'|None (None = no heal attempted).
    """
    if svc in ("skipped", "missing"):
        return svc, None
    if svc.lower() == "running":
        return svc, None
    ok, detail = _start_service(SERVICE_NAME)
    after = _service_state(SERVICE_NAME)
    if ok and after.lower() == "running":
        notes.append(
            f"local {SERVICE_NAME} healed Start-Service "
            f"(was Status={svc}; now Running)"
        )
        return after, "started"
    findings.append(
        f"local {SERVICE_NAME} Status={after or svc} after Start-Service "
        f"heal failed detail={detail!r} (want Running)"
    )
    return after or svc, "failed"


def check(args):
    chair, digest = resolve_homes(args)
    path = digest / "digest.json"
    findings: list[str] = []
    notes: list[str] = []
    now = time.time()
    max_age = DEFAULT_MAX_AGE_SEC

    svc = _service_state(SERVICE_NAME)
    heal_result: str | None = None
    if svc == "missing" and sys.platform == "win32":
        notes.append(f"local {SERVICE_NAME} service not installed on this host")
    else:
        svc, heal_result = _heal_local_ear(svc, findings, notes)

    machines_checked = 0
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            findings.append(f"digest.json unreadable: {type(e).__name__}")
            data = None
        machines = data.get("machines") if isinstance(data, dict) else None
        if isinstance(machines, dict):
            for mid, ent in machines.items():
                if not isinstance(ent, dict):
                    continue
                machines_checked += 1
                name = str(mid or "").strip() or "?"
                if _machine_ear_offline(ent):
                    findings.append(
                        f"{name}: ear-offline online={ent.get('online')!r} "
                        f"status={ent.get('status')!r}"
                    )
                    continue
                age = _parse_iso_age_s(ent.get("lastSeen") or ent.get("last_seen"), now)
                if age is not None and age > max_age:
                    findings.append(
                        f"{name}: lastSeen stale age_sec={int(age)} max={max_age}"
                    )
        else:
            notes.append("digest.json has no machines map")
    else:
        findings.append(f"digest.json missing: {path}")

    ok = not findings
    payload = {
        "ok": ok,
        "path": str(path),
        "service": SERVICE_NAME,
        "service_status": svc,
        "heal": heal_result,
        "machines_checked": machines_checked,
        "max_age_sec": max_age,
        "findings": findings,
        "notes": notes,
        "chair_home": str(chair),
    }
    return (payload, EXIT_OK if ok else EXIT_FINDING)


def main(argv=None) -> int:
    return run_check(
        "ircbob_ear",
        "ircBob Running + digest lastSeen / ear-offline + local Start-Service heal (FR #9144)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
