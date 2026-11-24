#!/usr/bin/env python3
"""Token-free disk starvation detect + auto-remediate (monitor disk_starvation).

Detects ``worktree-create-failed:disk`` / ``disk-low`` (FR #6240) from live
``GET /bob/v1/report`` offer_outcomes / giveup_reason, maps seats to machines,
optionally files a machine-pinned intake issue, and runs
``Invoke-BobiverseDiskStarvationRemediate.ps1`` (Clear + SeatDisk + orphan
bob-bridge worktrees) via local or WinRM.

EXIT 0: no disk starvation (or dry-run).
EXIT 1: finding (starvation seen; remediate attempted when auto on).
EXIT 2: error (bad fixture / remediator crash when required).

Env:
  BOB_DISK_STARVATION_AUTO=0     detect-only (default 1 = auto remediate)
  BOB_DISK_STARVATION_FILE=0     skip intake file (default 1)
  BOB_DISK_STARVATION_MIN_FREE_GB=8
  JEEVES_DISK_STARVATION_FIXTURE=/path/to.json
  BOB_REPORT_URL / BOB_MONITOR_REPORT_URL
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from _common import (
    EXIT_ERROR,
    EXIT_FINDING,
    EXIT_OK,
    build_parser,
    fetch_live_report,
    find_upward_file,
    live_report_url,
    run_check,
)

DISK_RX = re.compile(
    r"worktree-create-failed:\s*disk|disk-low|disk[_\s-]?full|no space left on device",
    re.I,
)
# Worktree path collision is not disk-low (FR #9710 storm from #9700 branch reuse).
_NOT_DISK_RX = re.compile(
    r"already used by worktree|is already checked out|worktree.*already exists",
    re.I,
)
SEAT_RX = re.compile(r"^([a-z0-9][a-z0-9_.]*?)-(\d+)$", re.I)
_USER_AGENT = "BobiverseJeevesMonitor-disk_starvation/1.0"


def auto_remediate_enabled(env: Optional[dict] = None) -> bool:
    env = os.environ if env is None else env
    raw = (env.get("BOB_DISK_STARVATION_AUTO") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def file_intake_enabled(env: Optional[dict] = None) -> bool:
    env = os.environ if env is None else env
    raw = (env.get("BOB_DISK_STARVATION_FILE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def min_free_gb(env: Optional[dict] = None) -> float:
    env = os.environ if env is None else env
    raw = (env.get("BOB_DISK_STARVATION_MIN_FREE_GB") or "").strip()
    if not raw:
        return 8.0
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 8.0


def machine_from_nick(nick: str) -> str:
    """Map seat nick -> machine id. Bare tokens (``f``, ``0``, ``,``) are not machines.

    FR #9710: giveup_seats garbage must not become machine-pinned intake titles.
    """
    s = (nick or "").strip().lower()
    if not s:
        return ""
    m = SEAT_RX.match(s)
    if m:
        return m.group(1).replace("_", "")
    # Hyphenated non-seat forms (rare): keep prefix only when both sides look real.
    if "-" in s:
        left, right = s.rsplit("-", 1)
        if left and right.isdigit() and len(left) >= 2:
            return left.replace("_", "")
    return ""


def is_fleet_machine_id(machine: str) -> bool:
    """True when ``machine`` is a plausible fleet shop id (not punctuation / 1-char)."""
    try:
        import registered_machines as rm

        mid = rm.normalize_machine_id(machine)
    except Exception:
        mid = (machine or "").strip().lower()
        if not mid or not re.match(r"^[a-z0-9][a-z0-9-]{0,62}$", mid, re.I):
            mid = None
    if not mid or len(mid) < 2:
        return False
    return True


def is_disk_reason(reason: str) -> bool:
    """Disk-low class reasons only — exclude worktree path collisions (FR #9710)."""
    text = str(reason or "")
    if not text or not DISK_RX.search(text):
        return False
    if _NOT_DISK_RX.search(text):
        return False
    return True


def iter_giveup_seats(raw) -> list[str]:
    """Normalize ``giveup_seats`` to discrete seat tokens (FR #9728).

    A JSON string value (e.g. ``\"flamingo\"``) must NOT be iterated as characters —
    that spawned WinRM/intake hosts ``f,l,a,m,i,n,g,o``.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, (list, tuple, set)):
        out: list[str] = []
        for x in raw:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    return []


def _coerce_rows(doc: dict) -> list[dict]:
    q = doc.get("queue") if isinstance(doc.get("queue"), dict) else {}
    out: list[dict] = []
    for key in ("unaccepted", "accepted", "offerable", "held"):
        raw = q.get(key)
        if isinstance(raw, list):
            out.extend([r for r in raw if isinstance(r, dict)])
        elif isinstance(raw, dict):
            out.extend([r for r in raw.values() if isinstance(r, dict)])
    return out


def _row_id(row: dict) -> str:
    raw = str(row.get("id") or row.get("number") or "").strip()
    if raw and not raw.startswith("#"):
        raw = "#" + raw
    repo = str(row.get("repo") or "").strip()
    if repo and raw:
        return f"{repo}{raw}"
    return raw or repo or "?"


def detect_disk_machines(doc: dict) -> dict[str, dict[str, Any]]:
    """Return machine -> {jobs, seats, reasons, sample_ts}."""
    hits: dict[str, dict[str, Any]] = {}

    def touch(machine: str, *, job: str, seat: str, reason: str, ts: str = "") -> None:
        mid = (machine or "").strip().lower()
        if not mid or not is_fleet_machine_id(mid):
            return
        slot = hits.setdefault(
            mid,
            {"machine": mid, "jobs": [], "seats": [], "reasons": [], "sample_ts": ""},
        )
        if job and job not in slot["jobs"]:
            slot["jobs"].append(job)
        if seat and seat not in slot["seats"]:
            slot["seats"].append(seat)
        if reason and reason not in slot["reasons"]:
            slot["reasons"].append(reason[:200])
        if ts and not slot["sample_ts"]:
            slot["sample_ts"] = ts

    for row in _coerce_rows(doc):
        job = _row_id(row)
        reason = str(row.get("giveup_reason") or "")
        if is_disk_reason(reason):
            for seat in iter_giveup_seats(row.get("giveup_seats")):
                touch(machine_from_nick(seat), job=job, seat=seat, reason=reason)
            # lingering reason with empty seats: infer from disk nacks in outcomes
            for o in row.get("offer_outcomes") or []:
                if not isinstance(o, dict):
                    continue
                oreason = str(o.get("reason") or "")
                if is_disk_reason(oreason):
                    seat = str(o.get("seat") or "")
                    touch(
                        machine_from_nick(seat),
                        job=job,
                        seat=seat,
                        reason=oreason,
                        ts=str(o.get("ts") or ""),
                    )
            continue
        for o in row.get("offer_outcomes") or []:
            if not isinstance(o, dict):
                continue
            oreason = str(o.get("reason") or "")
            if not is_disk_reason(oreason):
                continue
            seat = str(o.get("seat") or "")
            touch(
                machine_from_nick(seat),
                job=job,
                seat=seat,
                reason=oreason,
                ts=str(o.get("ts") or ""),
            )
    return hits


def _load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_remediator() -> Optional[Path]:
    env = (os.environ.get("BOB_DISK_STARVATION_REMEDIATE") or "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    found = find_upward_file(
        Path(__file__).resolve().parent,
        "common",
        "scripts",
        "Invoke-BobiverseDiskStarvationRemediate.ps1",
        max_levels=8,
    )
    if found:
        return found
    for cand in (
        Path(r"C:\ai\bob\common\scripts\Invoke-BobiverseDiskStarvationRemediate.ps1"),
        Path(r"D:\ai\bob\common\scripts\Invoke-BobiverseDiskStarvationRemediate.ps1"),
    ):
        if cand.is_file():
            return cand
    return None


def run_remediator(
    machine: str,
    *,
    dry_run: bool,
    min_gb: float,
    remediator: Path,
) -> dict[str, Any]:
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(remediator),
        "-Machine",
        machine,
        "-MinFreeGB",
        str(min_gb),
    ]
    if dry_run:
        cmd.append("-DryRun")
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "machine": machine, "error": f"{type(e).__name__}: {e}"}
    raw = (p.stdout or "").strip()
    # Last JSON line wins (warnings may precede).
    payload: dict[str, Any] = {
        "ok": p.returncode == 0,
        "machine": machine,
        "exit_code": p.returncode,
        "stderr": (p.stderr or "")[-500:],
    }
    for line in reversed(raw.splitlines() or [""]):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                doc = json.loads(line)
                if isinstance(doc, dict):
                    payload.update(doc)
                break
            except json.JSONDecodeError:
                continue
    else:
        payload["stdout_tail"] = raw[-500:]
    return payload


def _intake_stamp_path(machine: str) -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Bobiverse" / "monitor" / "disk_starvation"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{machine}.json"


def intake_cooldown_ok(machine: str, *, hours: float = 6.0) -> bool:
    path = _intake_stamp_path(machine)
    if not path.is_file():
        return True
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        ts = float(doc.get("ts") or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return True
    return (time.time() - ts) >= hours * 3600.0


def mark_intake_filed(machine: str, issue_hint: str = "") -> None:
    path = _intake_stamp_path(machine)
    path.write_text(
        json.dumps({"ts": time.time(), "machine": machine, "hint": issue_hint}, separators=(",", ":")),
        encoding="utf-8",
    )


def resolve_report_script() -> Optional[Path]:
    found = find_upward_file(
        Path(__file__).resolve().parent,
        "common",
        "scripts",
        "Report-BobiverseIntakeIssue.ps1",
        max_levels=8,
    )
    if found:
        return found
    for cand in (
        Path(r"C:\ai\bob\common\scripts\Report-BobiverseIntakeIssue.ps1"),
        Path(r"D:\ai\bob\common\scripts\Report-BobiverseIntakeIssue.ps1"),
    ):
        if cand.is_file():
            return cand
    return None


def file_machine_pinned_issue(
    machine: str,
    hit: dict[str, Any],
    *,
    remediate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if not is_fleet_machine_id(machine):
        return {"ok": True, "skipped": "invalid_machine", "machine": machine}
    script = resolve_report_script()
    if script is None:
        return {"ok": False, "error": "Report-BobiverseIntakeIssue.ps1 missing"}
    if not intake_cooldown_ok(machine):
        return {"ok": True, "skipped": "cooldown", "machine": machine}

    jobs = ", ".join(hit.get("jobs") or [])[:300]
    seats = ", ".join(hit.get("seats") or [])[:200]
    reasons = "; ".join(hit.get("reasons") or [])[:400]
    rem_txt = ""
    if isinstance(remediate, dict):
        rem_txt = (
            f"\n## Auto-remediate\n"
            f"- via: {remediate.get('via')}\n"
            f"- free_gb_before: {remediate.get('free_gb_before')}\n"
            f"- free_gb_after: {remediate.get('free_gb_after')}\n"
            f"- ok: {remediate.get('ok')}\n"
        )
    title = f"{machine}: disk starvation — worktree-create-failed:disk (auto)"
    if len(title) > 200:
        title = title[:200]
    body = (
        f"require_machine: {machine}\n\n"
        f"## What\n"
        f"Disk starvation on `{machine}` (worktree-create-failed:disk / disk-low FR #6240).\n"
        f"Machine-pinned for the Jeeves agent / monitor `disk_starvation` remediator.\n\n"
        f"## Evidence\n"
        f"- seats: {seats or '(from offer_outcomes)'}\n"
        f"- jobs: {jobs}\n"
        f"- reasons: {reasons}\n"
        f"- sample_ts: {hit.get('sample_ts') or ''}\n"
        f"{rem_txt}\n"
        f"## Fix\n"
        f"Run `Invoke-BobiverseDiskStarvationRemediate.ps1 -Machine {machine}` "
        f"(Clear-BobiverseJobWorktrees + Clear-BobiverseSeatDisk + orphan bob-bridge worktrees). "
        f"Then `!cleargiveup` disk-low rows for that machine.\n"
    )
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Repo",
        "SimonBarnett/bobiverse",
        "-Kind",
        "issue",
        "-Title",
        title,
        "-Body",
        body,
        "-Machine",
        machine,
        "-Agent",
        "disk_starvation-monitor",
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    ok = p.returncode == 0
    if ok:
        mark_intake_filed(machine, out[-200:])
    return {"ok": ok, "exit_code": p.returncode, "output_tail": out[-400:], "machine": machine}


def check(args: Any) -> tuple[dict[str, Any], int]:
    fix = (os.environ.get("JEEVES_DISK_STARVATION_FIXTURE") or "").strip()
    if fix:
        try:
            doc = _load_fixture(Path(fix))
            source = "fixture"
        except (OSError, json.JSONDecodeError) as exc:
            return (
                {
                    "ok": False,
                    "findings": [f"fixture read failed: {type(exc).__name__}"],
                    "path_fixture": fix,
                },
                EXIT_ERROR,
            )
    else:
        url = live_report_url()
        # Prefer public bob.ntsa.uk when default irc host differs
        env_url = (os.environ.get("BOB_REPORT_URL") or "").strip()
        doc = fetch_live_report(url=env_url or url or "https://bob.ntsa.uk/bob/v1/report")
        source = "live_report"
        if doc is None:
            return (
                {
                    "ok": True,
                    "soft_ok": True,
                    "reason": "report_unavailable",
                    "source": source,
                    "findings": [],
                },
                EXIT_OK,
            )

    hits = detect_disk_machines(doc if isinstance(doc, dict) else {})
    # Fixture may pass precomputed machines
    if isinstance(doc, dict) and isinstance(doc.get("disk_machines"), dict) and not hits:
        for mach, meta in doc["disk_machines"].items():
            mid = str(mach).lower()
            if not is_fleet_machine_id(mid) or not isinstance(meta, dict):
                continue
            hits[mid] = {
                "machine": mid,
                "jobs": list(meta.get("jobs") or []),
                "seats": list(meta.get("seats") or []),
                "reasons": list(meta.get("reasons") or ["fixture"]),
                "sample_ts": str(meta.get("sample_ts") or ""),
            }

    findings = [
        f"disk starvation on {m}: jobs={','.join(h.get('jobs') or [])[:120]} seats={','.join(h.get('seats') or [])}"
        for m, h in sorted(hits.items())
    ]

    remediations: dict[str, Any] = {}
    filings: dict[str, Any] = {}
    do_auto = auto_remediate_enabled() and not getattr(args, "dry_run", False)
    # build_parser dry-run already short-circuits; allow --detect-only via env only.
    remediator = resolve_remediator() if do_auto and hits else None
    min_gb = min_free_gb()

    if hits and do_auto:
        if remediator is None:
            findings.append("remediator script missing (Invoke-BobiverseDiskStarvationRemediate.ps1)")
        else:
            for mach, hit in sorted(hits.items()):
                rem = run_remediator(mach, dry_run=False, min_gb=min_gb, remediator=remediator)
                remediations[mach] = rem
                if file_intake_enabled():
                    filings[mach] = file_machine_pinned_issue(mach, hit, remediate=rem)
                if not rem.get("ok"):
                    findings.append(
                        f"remediate {mach} failed: {rem.get('error') or rem.get('free_gb_after')}"
                    )
    elif hits and file_intake_enabled() and not getattr(args, "dry_run", False):
        for mach, hit in sorted(hits.items()):
            filings[mach] = file_machine_pinned_issue(mach, hit)

    ok = not hits
    # Still EXIT 1 when we saw starvation (even if remediated) so the cycle records the incident.
    code = EXIT_OK if ok else EXIT_FINDING
    return (
        {
            "ok": ok,
            "source": source,
            "machines": sorted(hits.keys()),
            "hits": hits,
            "auto": do_auto,
            "remediator": str(remediator) if remediator else "",
            "remediations": remediations,
            "filings": filings,
            "findings": findings,
            "remediation": (
                "Invoke-BobiverseDiskStarvationRemediate.ps1 -Machine <id>; "
                "!cleargiveup disk-low rows; machine-pinned intake require_machine: <id>"
                if findings
                else ""
            ),
            "fr_hint": "disk_starvation monitor + machine-pinned Jeeves-agent issue",
        },
        code,
    )


def main(argv: Optional[list[str]] = None) -> int:
    return run_check(
        "disk_starvation",
        "Detect disk-low offer starvation and auto-run Clear/SeatDisk remediator",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
