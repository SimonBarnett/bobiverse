# -*- coding: utf-8 -*-
"""FR #9900: chair log freshness distinct from HTTP /health ok.

Walrus class (FR #8781): /health ok=true while NSSM stdout.log last-write is
stale. Digest write freshness does not prove AppStdout progress.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# 30 minutes: same ballpark as stuck-sweep / digest stale cues.
DEFAULT_MAX_AGE_SEC = 30 * 60


def progress_max_age_s(env: dict | None = None) -> float:
    env = os.environ if env is None else env
    raw = (env.get("BOB_CHAIR_PROGRESS_MAX_AGE_S") or "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return float(DEFAULT_MAX_AGE_SEC)


def file_mtime_age_s(path: Path, *, now: float | None = None) -> float | None:
    """Seconds since mtime, or None if missing/unreadable."""
    try:
        if not path.is_file():
            return None
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return float((time.time() if now is None else now) - mtime)


def candidate_install_roots(home: Path | None = None, env: dict | None = None) -> list[Path]:
    env = os.environ if env is None else env
    out: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path | None) -> None:
        if p is None:
            return
        try:
            key = str(p.resolve()).lower()
        except OSError:
            key = str(p).lower()
        if key in seen:
            return
        seen.add(key)
        out.append(p)

    for key in ("BOB_INSTALL_ROOT", "BOB_JEEVES_INSTALL", "BOB_TRAY_INSTALL_ROOT"):
        raw = (env.get(key) or "").strip()
        if raw:
            _add(Path(raw))
    # Chair home sibling: <ai>/jeeves when home is under <ai>/jeeves or ~/.jeeves
    if home is not None:
        try:
            parent = home.resolve().parent
        except OSError:
            parent = home.parent
        _add(parent)
        if parent.name.lower() in (".jeeves", "home"):
            _add(parent.parent)
            _add(parent.parent / "jeeves")
    for cand in (Path(r"C:\ai\jeeves"), Path(r"D:\ai\jeeves")):
        if cand.is_dir():
            _add(cand)
    return out


def log_paths(home: Path, *, install_roots: list[Path] | None = None) -> dict[str, Path]:
    """Named log paths: stdout (NSSM), cmd_trace (chair home)."""
    roots = install_roots if install_roots is not None else candidate_install_roots(home)
    stdout = None
    for root in roots:
        p = root / "logs" / "stdout.log"
        if p.is_file() or stdout is None:
            stdout = p
            if p.is_file():
                break
    return {
        "stdout": stdout or (roots[0] / "logs" / "stdout.log" if roots else home / "logs" / "stdout.log"),
        "cmd_trace": home / "cmd-trace.log",
    }


def progress_snapshot(
    home: Path,
    *,
    now: float | None = None,
    max_age_s: float | None = None,
    install_roots: list[Path] | None = None,
    env: dict | None = None,
) -> dict[str, Any]:
    """Return ages + progress_ok for /health and the chair_progress monitor.

    progress_ok is True when at least one present log is within max_age_s.
    Missing all logs => progress_ok True with soft note (cannot measure).
    """
    now_f = float(time.time() if now is None else now)
    max_age = float(progress_max_age_s(env) if max_age_s is None else max_age_s)
    paths = log_paths(home, install_roots=install_roots)
    ages: dict[str, float | None] = {}
    present = 0
    fresh = 0
    for name, path in paths.items():
        age = file_mtime_age_s(path, now=now_f)
        ages[f"{name}_age_s"] = None if age is None else round(age, 3)
        ages[f"{name}_path"] = str(path)
        if age is None:
            continue
        present += 1
        if age <= max_age:
            fresh += 1
    if present == 0:
        progress_ok = True
        reason = "no_log_files"
    elif fresh > 0:
        progress_ok = True
        reason = "fresh"
    else:
        progress_ok = False
        reason = "stale_logs"
    return {
        "progress_ok": progress_ok,
        "progress_reason": reason,
        "progress_max_age_s": max_age,
        "progress_present": present,
        "progress_fresh": fresh,
        **ages,
    }
