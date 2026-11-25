# -*- coding: utf-8 -*-
"""FR #9833: optional Jeeves-build dispatch lock (offer allowlist).

Default off. When on (mode ``build-jeeves``), !list / !bored / assign only admit:
* MRB/FIX rows whose ``changed_files`` are exclusively under ``jeeves/`` + ``common/``
* FR rows whose issue number is allowlisted (exact or prefix)
* Never harvest-lesson tips, TipForm-restore receipts, or other tasks

Operator: ``!focus build-jeeves on|off`` or ``dispatch-lock.json`` in digest home.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LOCK_FILE = "dispatch-lock.json"
MODE_BUILD_JEEVES = "build-jeeves"

# Gate FRs from FR #9833 / #9821 family (operator can extend via file).
_DEFAULT_ALLOW_FR = (9821, 9826, 9771, 9772)
_DEFAULT_ALLOW_FR_PREFIXES = ("978",)
_DEFAULT_PATH_PREFIXES = ("jeeves/", "common/")

_HARVEST_LESSON_RE = re.compile(r"(?i)^\s*lesson\s*\(")


def _empty() -> dict[str, Any]:
    return {
        "v": 1,
        "on": False,
        "mode": MODE_BUILD_JEEVES,
        "path_prefixes": list(_DEFAULT_PATH_PREFIXES),
        "allow_fr": list(_DEFAULT_ALLOW_FR),
        "allow_fr_prefixes": list(_DEFAULT_ALLOW_FR_PREFIXES),
    }


def lock_path(home: Path) -> Path:
    return Path(home).expanduser() / LOCK_FILE


def load_lock(home: Path) -> dict[str, Any]:
    path = lock_path(home)
    doc = _empty()
    if not path.is_file():
        return doc
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return doc
    if not isinstance(raw, dict):
        return doc
    doc["on"] = bool(raw.get("on"))
    mode = str(raw.get("mode") or MODE_BUILD_JEEVES).strip() or MODE_BUILD_JEEVES
    doc["mode"] = mode
    prefs = raw.get("path_prefixes")
    if isinstance(prefs, list) and prefs:
        doc["path_prefixes"] = [
            str(p).replace("\\", "/").lstrip("/").lower()
            for p in prefs
            if str(p).strip()
        ]
    allow = raw.get("allow_fr")
    if isinstance(allow, list):
        nums: list[int] = []
        for x in allow:
            try:
                n = int(str(x).strip().lstrip("#"))
            except (TypeError, ValueError):
                continue
            if n > 0:
                nums.append(n)
        if nums:
            doc["allow_fr"] = nums
    prefixes = raw.get("allow_fr_prefixes")
    if isinstance(prefixes, list) and prefixes:
        doc["allow_fr_prefixes"] = [str(p).strip() for p in prefixes if str(p).strip()]
    return doc


def save_lock(home: Path, doc: dict[str, Any]) -> None:
    path = lock_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = _empty()
    out.update({k: doc.get(k, out[k]) for k in out})
    out["on"] = bool(doc.get("on"))
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def is_on(home: Path) -> bool:
    doc = load_lock(home)
    return bool(doc.get("on")) and str(doc.get("mode") or "") == MODE_BUILD_JEEVES


def set_build_jeeves(home: Path, on: bool) -> dict[str, Any]:
    doc = load_lock(home)
    doc["on"] = bool(on)
    doc["mode"] = MODE_BUILD_JEEVES
    if not doc.get("path_prefixes"):
        doc["path_prefixes"] = list(_DEFAULT_PATH_PREFIXES)
    if not doc.get("allow_fr"):
        doc["allow_fr"] = list(_DEFAULT_ALLOW_FR)
    if not doc.get("allow_fr_prefixes"):
        doc["allow_fr_prefixes"] = list(_DEFAULT_ALLOW_FR_PREFIXES)
    save_lock(home, doc)
    return doc


def _canon_task(row: dict) -> str:
    task = str(row.get("task") or "FR").upper()
    if task == "PR":
        task = "FR"
    return task


def _row_number(row: dict) -> int | None:
    raw = str(row.get("id") or row.get("number") or "").strip().lstrip("#")
    if raw.isdigit():
        return int(raw)
    return None


def _changed_paths(row: dict) -> list[str]:
    raw = row.get("changed_files") or row.get("files") or row.get("paths") or []
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            p = item.replace("\\", "/").lstrip("/")
        elif isinstance(item, dict):
            p = str(item.get("filename") or item.get("path") or "").replace("\\", "/").lstrip("/")
        else:
            p = ""
        if p:
            out.append(p)
    return out


def _paths_ok(paths: list[str], prefixes: list[str]) -> bool:
    if not paths:
        return False
    prefs = [p.lower() if p.endswith("/") else (p.lower() + "/") for p in prefixes]
    for path in paths:
        pl = path.lower()
        if not any(pl.startswith(pref) or pl == pref.rstrip("/") for pref in prefs):
            return False
    return True


def _fr_allowlisted(num: int | None, doc: dict[str, Any]) -> bool:
    if num is None or num <= 0:
        return False
    allow = {int(x) for x in (doc.get("allow_fr") or []) if str(x).strip()}
    if num in allow:
        return True
    s = str(num)
    for pref in doc.get("allow_fr_prefixes") or []:
        p = str(pref).strip()
        if p and s.startswith(p):
            return True
    return False


def _is_harvest_lesson(row: dict) -> bool:
    if row.get("harvest_lesson") in (True, 1, "1", "true", "True"):
        return True
    labs = row.get("labels") or []
    names: list[str] = []
    if isinstance(labs, str):
        names = [x.strip().lower() for x in labs.split(",") if x.strip()]
    elif isinstance(labs, list):
        for item in labs:
            if isinstance(item, str):
                names.append(item.strip().lower())
            elif isinstance(item, dict):
                names.append(str(item.get("name") or "").strip().lower())
    if "harvest-lesson" in names:
        return True
    title = str(row.get("title") or "")
    return bool(_HARVEST_LESSON_RE.match(title))


def row_blocked_reason(home: Path, row: dict) -> str | None:
    """Return a short skip reason when dispatch lock blocks this row, else None."""
    if not isinstance(row, dict) or not is_on(home):
        return None
    doc = load_lock(home)
    task = _canon_task(row)
    if _is_harvest_lesson(row):
        return "dispatch-lock:harvest-lesson"
    if task in ("MRB", "FIX"):
        paths = _changed_paths(row)
        prefs = list(doc.get("path_prefixes") or _DEFAULT_PATH_PREFIXES)
        if _paths_ok(paths, prefs):
            return None
        return "dispatch-lock:path"
    if task == "FR":
        if _fr_allowlisted(_row_number(row), doc):
            return None
        return "dispatch-lock:fr"
    # UAT / BUILD / other — not part of tip-build allowlist
    return "dispatch-lock:task"


def status_line(home: Path) -> str:
    doc = load_lock(home)
    state = "on" if doc.get("on") else "off"
    return f"dispatch-lock {doc.get('mode')}: {state}"


def clear_off_list_accepted(
    home: Path,
    *,
    nick: str | None = None,
    load_queue=None,
    write_queue=None,
    queue_path=None,
) -> int:
    """FR #9875: under build-jeeves lock, return off-list accepted rows to unaccepted.

    When a tip-allowlisted job is (or was) assigned, nested digest / tray FRs that
    slipped into ``accepted`` must not keep the seat NAK-busy. Optional ``nick``
    limits the clear to that seat's accepted rows.
    """
    if not is_on(home):
        return 0
    try:
        import gitclaim as gc
    except Exception:
        return 0
    _load = load_queue or gc.load_queue
    _write = write_queue or gc._write_queue
    _qpath = queue_path or gc.queue_path
    doc = _load(home)
    if not isinstance(doc, dict):
        return 0
    accepted = list(doc.get("accepted") or [])
    if not accepted:
        return 0
    nick_l = (nick or "").strip().lower()
    keep: list[dict] = []
    moved: list[dict] = []
    for row in accepted:
        if not isinstance(row, dict):
            continue
        if nick_l:
            holders = {
                str(row.get("accepted_by") or "").strip().lower(),
                str(row.get("nick") or "").strip().lower(),
                str(row.get("offered_to") or "").strip().lower(),
            }
            if nick_l not in holders:
                keep.append(row)
                continue
        if row_blocked_reason(home, row) is None:
            keep.append(row)
            continue
        # Return to unaccepted so tip work can proceed; strip accept stamps.
        back = dict(row)
        for k in (
            "accepted_by",
            "accepted_ts",
            "accepted_channel",
            "nick",
            "offered_to",
            "offered_ts",
            "offered_channel",
        ):
            back.pop(k, None)
        back["requeued_via"] = "dispatch-lock-offlist"
        moved.append(back)
    if not moved:
        return 0
    unacc = [r for r in (doc.get("unaccepted") or []) if isinstance(r, dict)]
    # Avoid duplicate unaccepted keys.
    seen = {
        (
            str(r.get("repo") or "").lower(),
            str(r.get("task") or "").upper(),
            str(r.get("id") or "").lstrip("#"),
        )
        for r in unacc
    }
    for row in moved:
        key = (
            str(row.get("repo") or "").lower(),
            str(row.get("task") or "").upper(),
            str(row.get("id") or "").lstrip("#"),
        )
        if key not in seen:
            unacc.append(row)
            seen.add(key)
    doc["accepted"] = keep
    doc["unaccepted"] = unacc
    _write(_qpath(home), doc)
    return len(moved)
