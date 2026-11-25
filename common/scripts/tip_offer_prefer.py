"""FR #9850 / #9867: tip-allowlist offer prefer for DIRTY FIX and CLEAN tip MRB.

Chair offer ranking and intervene_assign must prefer:
* tip-allowlist FIX when merge state is DIRTY/CONFLICTING (fold main before the
  tip merge gate counts the PR)
* tip-allowlist CLEAN/MERGEABLE MRB ahead of harvest-lesson FRs

Tip membership: ``BOB_TIP_ALLOWLIST`` (comma numbers), optional ``tip-allowlist.json``
under digest home, or ``changed_files`` exclusively under tip path prefixes
(``jeeves/``, ``common/``). Override prefixes with ``BOB_TIP_PATH_PREFIXES``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

RANK_TIP_DIRTY_FIX = 0
RANK_TIP_CLEAN_MRB = 1
RANK_TIP_OTHER = 2
RANK_NORMAL = 3
RANK_HARVEST_LESSON_FR = 4

_DEFAULT_PATH_PREFIXES = ("jeeves/", "common/")
_HARVEST_LESSON_RE = re.compile(r"(?i)^\s*lesson\s*\(")
_ALLOWLIST_FILE = "tip-allowlist.json"

_DIRTY_STATES = frozenset({"DIRTY", "CONFLICTING"})
_CLEAN_STATES = frozenset({"CLEAN", "MERGEABLE", "HAS_HOOKS"})


def _canon_task(row: dict) -> str:
    task = str(row.get("task") or row.get("type") or "FR").strip().upper()
    if task == "PR":
        task = "MRB"
    return task


def _row_number(row: dict) -> int | None:
    raw = str(row.get("id") or row.get("number") or "").strip().lstrip("#")
    if raw.isdigit():
        return int(raw)
    return None


def _label_names(row: dict) -> list[str]:
    labels = row.get("labels") or []
    if isinstance(labels, str):
        labels = [labels]
    names: list[str] = []
    for lab in labels:
        if isinstance(lab, dict):
            names.append(str(lab.get("name") or "").strip().lower())
        else:
            names.append(str(lab or "").strip().lower())
    return names


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


def tip_path_prefixes() -> tuple[str, ...]:
    raw = (os.environ.get("BOB_TIP_PATH_PREFIXES") or "").strip()
    if not raw:
        return _DEFAULT_PATH_PREFIXES
    parts = [p.replace("\\", "/").lstrip("/").lower() for p in raw.split(",") if p.strip()]
    return tuple(parts) or _DEFAULT_PATH_PREFIXES


def _paths_tip_ok(paths: Sequence[str], prefixes: Sequence[str] | None = None) -> bool:
    if not paths:
        return False
    prefs = prefixes if prefixes is not None else tip_path_prefixes()
    norm = [p.lower() if p.endswith("/") else (p.lower() + "/") for p in prefs]
    for path in paths:
        pl = path.lower()
        if not any(pl.startswith(pref) or pl == pref.rstrip("/") for pref in norm):
            return False
    return True


def tip_allowlist_numbers(home: Path | None = None) -> tuple[int, ...]:
    """Ordered unique tip PR/FR numbers from env and optional tip-allowlist.json."""
    nums: list[int] = []
    seen: set[int] = set()

    def _add(n: int) -> None:
        if n > 0 and n not in seen:
            seen.add(n)
            nums.append(n)

    raw = (os.environ.get("BOB_TIP_ALLOWLIST") or "").strip()
    if raw:
        for part in raw.split(","):
            part = part.strip().lstrip("#")
            if part.isdigit():
                _add(int(part))
    if home is not None:
        path = Path(home).expanduser() / _ALLOWLIST_FILE
        if path.is_file():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                doc = None
            if isinstance(doc, dict):
                for key in ("allow", "numbers", "prs", "frs"):
                    val = doc.get(key)
                    if isinstance(val, list):
                        for x in val:
                            try:
                                _add(int(str(x).strip().lstrip("#")))
                            except (TypeError, ValueError):
                                continue
            elif isinstance(doc, list):
                for x in doc:
                    try:
                        _add(int(str(x).strip().lstrip("#")))
                    except (TypeError, ValueError):
                        continue
    return tuple(nums)


def is_dirty_or_conflicting(row: dict) -> bool:
    """True when the row is stamped DIRTY/CONFLICTING or labelled fix-conflict."""
    if not isinstance(row, dict):
        return False
    names = _label_names(row)
    if "fix-conflict" in names:
        return True
    title = str(row.get("title") or "")
    if re.search(r"(?i)\bFIX\s+conflict\b", title):
        return True
    mergeable = row.get("mergeable")
    if str(mergeable or "").strip().upper() == "CONFLICTING":
        return True
    if mergeable is False or str(mergeable).strip().lower() == "false":
        st = str(
            row.get("mergeable_state") or row.get("mergeStateStatus") or ""
        ).strip().upper()
        if st in _DIRTY_STATES or st in ("", "UNKNOWN"):
            return True
    st = str(
        row.get("mergeable_state") or row.get("mergeStateStatus") or ""
    ).strip().upper()
    return st in _DIRTY_STATES


def is_mergeable_clean(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if row.get("mergeable") is True:
        return True
    st = str(
        row.get("mergeable_state") or row.get("mergeStateStatus") or ""
    ).strip().upper()
    return st in _CLEAN_STATES


def is_harvest_lesson_fr(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if _canon_task(row) != "FR":
        return False
    if row.get("harvest_lesson") in (True, 1, "1", "true", "True"):
        return True
    if "harvest-lesson" in _label_names(row):
        return True
    return bool(_HARVEST_LESSON_RE.match(str(row.get("title") or "")))


def row_is_tip_allowlisted(
    row: dict,
    *,
    allow: Iterable[int] | None = None,
    home: Path | None = None,
) -> bool:
    """True when the row is on the tip allowlist (number or tip path prefixes)."""
    if not isinstance(row, dict):
        return False
    nums = set(allow) if allow is not None else set(tip_allowlist_numbers(home))
    n = _row_number(row)
    if n is not None and n in nums:
        return True
    return _paths_tip_ok(_changed_paths(row))


def tip_prefer_rank(
    row: dict,
    *,
    allow: Iterable[int] | None = None,
    home: Path | None = None,
) -> int:
    """Lower sorts first in offer_sort_key / intervene plan_assigns.

    0 tip DIRTY/CONFLICTING FIX, 1 tip CLEAN MRB, 2 other tip MRB/FIX,
    3 normal work, 4 harvest-lesson FR (starves tip least).
    """
    if not isinstance(row, dict):
        return RANK_NORMAL
    if is_harvest_lesson_fr(row):
        return RANK_HARVEST_LESSON_FR
    tip_row = row_is_tip_allowlisted(row, allow=allow, home=home)
    task = _canon_task(row)
    if tip_row and task == "FIX" and is_dirty_or_conflicting(row):
        return RANK_TIP_DIRTY_FIX
    if tip_row and task == "MRB" and is_mergeable_clean(row):
        return RANK_TIP_CLEAN_MRB
    if tip_row and task in ("MRB", "FIX"):
        return RANK_TIP_OTHER
    return RANK_NORMAL
