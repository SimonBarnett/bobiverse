"""FR #5164: file one deduped bobiverse issue per stall fingerprint.

Never raises. Token-less / 403 / rate-limit -> local spool. Rate window per
fingerprint plus a global issues-per-hour cap.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

import crash_report

REPO = "SimonBarnett/bobiverse"
STATE_NAME = "stall-filer.json"
SPOOL_NAME = "stall-spool.jsonl"
FP_COOLDOWN_S = 6 * 3600
COMMENT_S = 30 * 60
GLOBAL_PER_HOUR = 4
FP_MARKER = "<!-- stall-fp:{fp} -->"


def state_path(home: Path) -> Path:
    return Path(home) / STATE_NAME


def spool_path(home: Path) -> Path:
    return Path(home) / SPOOL_NAME


def load_state(home: Path) -> dict[str, Any]:
    p = state_path(home)
    if not p.is_file():
        return {"fps": {}, "hour": 0, "hour_count": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"fps": {}, "hour": 0, "hour_count": 0}
    except Exception:
        return {"fps": {}, "hour": 0, "hour_count": 0}


def save_state(home: Path, state: dict[str, Any]) -> None:
    state_path(home).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _hour_bucket(now: float) -> int:
    return int(now // 3600)


def _dedupe_key(fp: str) -> str:
    return hashlib.sha256(fp.encode("utf-8")).hexdigest()[:32]


def issue_body(finding: dict[str, Any], *, excerpt: str = "") -> str:
    fp = str(finding.get("fingerprint") or "")
    ev = finding.get("evidence") or {}
    redacted = crash_report.redact(json.dumps(ev, indent=2)[:4000])
    log_bit = crash_report.redact((excerpt or "")[-2000:])
    return (
        f"{FP_MARKER.format(fp=fp)}\n"
        f"fingerprint=`{fp}`\n"
        f"detector=`{finding.get('id')}` key=`{finding.get('key')}`\n\n"
        f"## Evidence\n```json\n{redacted}\n```\n"
        f"## Log excerpt\n```\n{log_bit}\n```\n"
        f"\n---\n_via-intake FR=#5164 stall detector_\n"
    )


def apply_findings(
    findings: list[dict[str, Any]],
    *,
    home: Path,
    now: float | None = None,
    excerpt: str = "",
    list_open: Callable[[str], list[dict[str, Any]]] | None = None,
    comment: Callable[[int, str], Any] | None = None,
    create: Callable[[str, str], Any] | None = None,
    cooldown_s: float = FP_COOLDOWN_S,
    comment_s: float = COMMENT_S,
    global_per_hour: int = GLOBAL_PER_HOUR,
) -> list[dict[str, Any]]:
    """Process findings. Returns action records. Never raises."""
    actions: list[dict[str, Any]] = []
    try:
        now_f = time.time() if now is None else float(now)
        state = load_state(home)
        hour = _hour_bucket(now_f)
        if int(state.get("hour") or 0) != hour:
            state["hour"] = hour
            state["hour_count"] = 0
        fps = state.setdefault("fps", {})
        if not isinstance(fps, dict):
            fps = {}
            state["fps"] = fps

        for finding in findings or []:
            fp = str(finding.get("fingerprint") or "")
            if not fp:
                continue
            prev = fps.get(fp) if isinstance(fps.get(fp), dict) else {}
            last_at = float(prev.get("last_at") or 0)
            last_c = float(prev.get("last_comment_at") or 0)
            issue_n = prev.get("issue")

            twin = None
            if list_open is not None:
                try:
                    for iss in list_open(fp) or []:
                        if iss:
                            twin = iss
                            break
                except Exception as exc:  # noqa: BLE001
                    actions.append({"fp": fp, "action": "list_error", "error": type(exc).__name__})

            if twin and comment is not None:
                if last_c and (now_f - last_c) < comment_s:
                    actions.append({"fp": fp, "action": "deduped", "issue": twin.get("number")})
                    continue
                try:
                    comment(int(twin.get("number")), issue_body(finding, excerpt=excerpt)[:4000])
                    fps[fp] = {
                        "last_at": last_at or now_f,
                        "last_comment_at": now_f,
                        "issue": int(twin.get("number")),
                    }
                    actions.append({"fp": fp, "action": "comment", "issue": int(twin["number"])})
                except Exception as exc:  # noqa: BLE001
                    _spool(home, finding, excerpt, why=str(type(exc).__name__))
                    actions.append({"fp": fp, "action": "spool", "error": type(exc).__name__})
                continue

            if last_at and (now_f - last_at) < cooldown_s:
                actions.append({"fp": fp, "action": "cooldown"})
                continue
            if int(state.get("hour_count") or 0) >= global_per_hour:
                actions.append({"fp": fp, "action": "capped"})
                continue

            title = str(finding.get("title") or fp)[:200]
            body = issue_body(finding, excerpt=excerpt)
            if create is None:
                _spool(home, finding, excerpt, why="no_create")
                actions.append({"fp": fp, "action": "spool", "error": "no_create"})
                continue
            try:
                created = create(title, body)
                num = None
                if isinstance(created, dict):
                    num = created.get("number")
                fps[fp] = {"last_at": now_f, "last_comment_at": now_f, "issue": num}
                state["hour_count"] = int(state.get("hour_count") or 0) + 1
                actions.append({"fp": fp, "action": "created", "issue": num})
            except Exception as exc:  # noqa: BLE001
                _spool(home, finding, excerpt, why=str(type(exc).__name__))
                actions.append({"fp": fp, "action": "spool", "error": type(exc).__name__})

        save_state(home, state)
    except Exception as exc:  # noqa: BLE001
        actions.append({"action": "fatal", "error": type(exc).__name__})
    return actions


def _spool(home: Path, finding: dict[str, Any], excerpt: str, *, why: str) -> None:
    line = json.dumps(
        {
            "why": why,
            "finding": finding,
            "excerpt": crash_report.redact(excerpt or "")[:2000],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        ensure_ascii=True,
    )
    p = spool_path(home)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def default_create(title: str, body: str) -> dict[str, Any]:
    fp = ""
    for line in body.splitlines():
        if line.startswith("fingerprint="):
            fp = line.split("`", 2)[1] if "`" in line else ""
            break
    sig = _dedupe_key(fp or title)
    return crash_report._post_intake(title, body, repo=REPO, sig=sig, exe="jeeves-stall")
