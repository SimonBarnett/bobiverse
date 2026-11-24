#!/usr/bin/env python3
"""FR #9144 / #9496: token-free ircBob ear / digest offline check + local auto-heal.

Chair path: digest machines with online=false, status \"I am offline\", or stale
lastSeen. Local path (win32): Get-Service ircBob; when Stopped, Start-Service
once and re-check (monitor auto-heal).

FR #9496: when Status=Running but no bob-ear.exe / irc_agent.py child is present,
EXIT 1 with finding and attempt Restart-Service once (Start-Service is a no-op
while Running). Also scan install logs/stderr for recent ENOSPC / errno 28 and
raise a loud finding. TipForm wording for ear-offline vs unreachable lives in
Get-BobTrayHover.ps1.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check
from ear_down_gate import ear_down_gate

DEFAULT_MAX_AGE_SEC = 900  # align with stale_digest
SERVICE_NAME = "ircBob"
DEFAULT_INSTALL = Path(r"C:\ai\bob")
ENOSPC_TAIL_BYTES = 256 * 1024
ENOSPC_RE = re.compile(
    r"(?i)(?:no space left on device|\bENOSPC\b|\[Errno\s*28\]|WinError\s*(?:112|39)\b|"
    r"not enough space on the disk)"
)


def _local_machine_id() -> str:
    """Folded digest machine id for this host (FR #9503 gate)."""
    raw = (
        os.environ.get("DIGEST_ID")
        or os.environ.get("BOB_MACHINE_ID")
        or os.environ.get("COMPUTERNAME")
        or ""
    ).strip()
    if not raw:
        return ""
    try:
        import bobreport

        return bobreport.fold_machine_id(raw) or raw.lower()
    except Exception:
        return raw.lower()
_EAR_CHILD_PS = (
    "@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
    "Where-Object { $_.CommandLine -and ("
    "($_.CommandLine -match 'irc_agent\\.py' -and $_.CommandLine -match 'bobiverse') -or "
    "($_.CommandLine -match 'bob-ear\\.exe') -or "
    "($_.Name -match '(?i)^bob-ear')"
    ") }).Count"
)


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


def _restart_service(name: str) -> tuple[bool, str]:
    """Local Restart-Service heal for Running-without-child (FR #9496).

    Never touches Ergo / BobIrcd. Returns (ok, detail).
    """
    if sys.platform != "win32":
        return False, "skipped"
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Restart-Service -Name '{name}' -Force -ErrorAction Stop; "
                f"Start-Sleep -Seconds 2; "
                f"(Get-Service -Name '{name}').Status",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0 and out.lower() == "running":
            return True, out
        detail = out or err or f"exit={r.returncode}"
        return False, detail[:240]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _ear_child_alive() -> bool:
    """True when a bob-ear.exe or irc_agent.py (bobiverse) process is present."""
    if sys.platform != "win32":
        return True  # non-win: skip local child gate
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _EAR_CHILD_PS],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = (r.stdout or "").strip()
        return int(raw or "0") > 0
    except Exception:
        return False


def _install_root() -> Path:
    raw = (
        os.environ.get("BOB_INSTALL_ROOT")
        or os.environ.get("BOB_TRAY_INSTALL_ROOT")
        or ""
    ).strip()
    if raw:
        return Path(raw)
    return DEFAULT_INSTALL


def _scan_enospc_logs() -> list[str]:
    """Return finding strings for recent ENOSPC / errno 28 in install logs (FR #9496)."""
    root = _install_root()
    hits: list[str] = []
    candidates = [
        root / "logs" / "stderr.log",
        root / "logs" / "stdout.log",
        root / "home" / "stderr.log",
        root / "home" / "stdout.log",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            with path.open("rb") as fh:
                if size > ENOSPC_TAIL_BYTES:
                    fh.seek(size - ENOSPC_TAIL_BYTES)
                data = fh.read()
            text = data.decode("utf-8", errors="replace")
        except OSError:
            continue
        m = ENOSPC_RE.search(text)
        if not m:
            continue
        snippet = m.group(0).replace("\n", " ").strip()
        hits.append(f"{path.name}: {snippet}")
        if len(hits) >= 3:
            break
    return hits


def _machine_ear_offline(ent: dict) -> bool:
    if not isinstance(ent, dict):
        return False
    if ent.get("online") is False:
        return True
    status = str(ent.get("status") or "").strip().lower()
    if "i am offline" in status or status == "offline":
        return True
    return False


def _heal_local_ear(
    svc: str,
    findings: list[str],
    notes: list[str],
    *,
    child_alive: bool | None = None,
) -> tuple[str, str | None, bool | None]:
    """Heal Stopped via Start-Service; Paused / Running-without-child via Restart-Service.

    FR #9863: NSSM AppThrottle after an unexpected bob-ear child kill leaves
    ``Get-Service ircBob`` as **Paused**. ``Start-Service`` does not clear Pause;
    only ``Restart-Service`` brings the ear back. Never ``Stop-Process`` the
    service ear under NSSM — use ``Restart-Service ircBob`` / ``Restart-BobEar.ps1``.

    Returns (status_after, heal_result, ear_child_alive).
    heal_result: 'started'|'restarted'|'failed'|None.
    """
    if svc in ("skipped", "missing"):
        return svc, None, child_alive

    st = (svc or "").strip().lower()

    # FR #9863: Paused / PausePending — AppThrottle after twin kill or crash loop.
    if st in ("paused", "pausepending"):
        findings.append(
            f"local {SERVICE_NAME} Status={svc} "
            f"(NSSM AppThrottle / unexpected ear death; FR #9863 — never Stop-Process "
            f"bob-ear under NSSM; use Restart-Service)"
        )
        ok, detail = _restart_service(SERVICE_NAME)
        after = _service_state(SERVICE_NAME)
        alive_after = _ear_child_alive()
        if ok and after.lower() == "running" and alive_after:
            notes.append(
                f"local {SERVICE_NAME} healed Restart-Service "
                f"(was Status={svc}; now Running + ear child; FR #9863)"
            )
            findings[:] = [
                f
                for f in findings
                if "FR #9863" not in f
            ]
            return after, "restarted", True
        findings.append(
            f"local {SERVICE_NAME} Restart-Service heal failed "
            f"status={after or svc} child_alive={alive_after} detail={detail!r} "
            f"(FR #9863 Paused)"
        )
        return after or svc, "failed", alive_after

    if st != "running":
        ok, detail = _start_service(SERVICE_NAME)
        after = _service_state(SERVICE_NAME)
        if ok and after.lower() == "running":
            notes.append(
                f"local {SERVICE_NAME} healed Start-Service "
                f"(was Status={svc}; now Running)"
            )
            alive = _ear_child_alive() if child_alive is None else child_alive
            return after, "started", alive
        findings.append(
            f"local {SERVICE_NAME} Status={after or svc} after Start-Service "
            f"heal failed detail={detail!r} (want Running)"
        )
        return after or svc, "failed", child_alive

    # FR #9496: Running without App child is a false-healthy nssm state.
    alive = _ear_child_alive() if child_alive is None else bool(child_alive)
    if alive:
        return svc, None, True

    findings.append(
        f"local {SERVICE_NAME} Running without bob-ear child "
        f"(bob-ear.exe / irc_agent.py absent; FR #9496)"
    )
    ok, detail = _restart_service(SERVICE_NAME)
    after = _service_state(SERVICE_NAME)
    alive_after = _ear_child_alive()
    if ok and after.lower() == "running" and alive_after:
        notes.append(
            f"local {SERVICE_NAME} healed Restart-Service "
            f"(was Running-without-child; now Running + ear child)"
        )
        # Drop the pre-heal finding — heal succeeded.
        findings[:] = [
            f
            for f in findings
            if "Running without bob-ear child" not in f
        ]
        return after, "restarted", True
    findings.append(
        f"local {SERVICE_NAME} Restart-Service heal failed "
        f"status={after or svc} child_alive={alive_after} detail={detail!r}"
    )
    return after or svc, "failed", alive_after



def check(args):
    chair, digest = resolve_homes(args)
    path = digest / "digest.json"
    findings: list[str] = []
    notes: list[str] = []
    now = time.time()
    max_age = DEFAULT_MAX_AGE_SEC

    svc = _service_state(SERVICE_NAME)
    heal_result: str | None = None
    ear_child: bool | None = None
    if svc == "missing" and sys.platform == "win32":
        notes.append(f"local {SERVICE_NAME} service not installed on this host")
    else:
        svc, heal_result, ear_child = _heal_local_ear(
            svc, findings, notes, child_alive=None
        )

    enospc_hits = _scan_enospc_logs()
    for hit in enospc_hits:
        findings.append(f"ENOSPC in ear log: {hit} (FR #9496; heal disk/temp)")

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

    # FR #9503: local heal alone is not EXIT_OK — digest must show this host
    # online with fresh lastSeen while bob-ear child is alive. Prevents closing
    # ear-down FRs (Closes) when nssm was restarted but the ear never rejoined.
    # Only apply on hosts that run ircBob (Running / healed / child probed).
    gate: dict | None = None
    local_mid = _local_machine_id()
    apply_gate = bool(local_mid) and path.is_file() and (
        (isinstance(svc, str) and svc.lower() == "running")
        or heal_result in ("started", "restarted", "failed")
        or ear_child is not None
    )
    if apply_gate:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            data = None
        machines = data.get("machines") if isinstance(data, dict) else None
        ent = None
        if isinstance(machines, dict):
            for mid, candidate in machines.items():
                if str(mid or "").strip().lower() == local_mid.lower():
                    ent = candidate if isinstance(candidate, dict) else None
                    break
                try:
                    import bobreport

                    if bobreport.fold_machine_id(mid) == local_mid:
                        ent = candidate if isinstance(candidate, dict) else None
                        break
                except Exception:
                    pass
        # Skip gate when this host is not in the digest map (fixture / remote-only
        # chair view). Gate applies when we are verifying *this* machine's ear.
        if ent is not None:
            gate = ear_down_gate(
                ear_child_alive=ear_child,
                machine_ent=ent,
                now=now,
                max_age_sec=max_age,
                startworker_acked=None,
            )
            if not gate.get("ok"):
                for reason in gate.get("reasons") or []:
                    msg = f"FR #9503 ear-down gate: {reason} (machine={local_mid})"
                    if msg not in findings:
                        findings.append(msg)

    ok = not findings
    payload = {
        "ok": ok,
        "path": str(path),
        "service": SERVICE_NAME,
        "service_status": svc,
        "heal": heal_result,
        "ear_child_alive": ear_child,
        "enospc": bool(enospc_hits),
        "machines_checked": machines_checked,
        "max_age_sec": max_age,
        "ear_down_gate": gate,
        "local_machine_id": local_mid or None,
        "findings": findings,
        "notes": notes,
        "chair_home": str(chair),
    }
    return (payload, EXIT_OK if ok else EXIT_FINDING)


def main(argv=None) -> int:
    return run_check(
        "ircbob_ear",
        "ircBob Running+child / digest lastSeen / ENOSPC logs + local heal (FR #9144/#9496)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
