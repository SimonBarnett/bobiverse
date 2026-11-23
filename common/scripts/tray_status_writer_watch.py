# -*- coding: utf-8 -*-
"""FR #9280: pure tray-status.json vs tray.alive / starting-stuck evaluator.

Mirrors bob/tray/dialogs/BobTray.cs TrayStatusWriterWatch for unit tests without a rebuild.
Never starts, stops, or retargets worker seats.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ALIVE_FRESH_SECONDS = 30.0
STARTING_STUCK_SECONDS = 180.0
STATUS_WRITE_INTERVAL_SECONDS = 15.0
STATUS_STALE_MULTIPLES = 8.0  # 8 * 15 = 120
STATUS_STALE_SECONDS = 120.0


def is_starting_seed(short_or_title: str | None) -> bool:
    return (short_or_title or "").strip().lower() == "starting"


def read_short_or_title(snap_path: str | Path | None) -> str:
    if not snap_path:
        return ""
    p = Path(snap_path)
    if not p.is_file():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    short = str(data.get("short") or "").strip()
    if short:
        return short
    return str(data.get("title") or "").strip()


def alive_is_fresh(
    alive_path: str | Path | None,
    *,
    now: float | None = None,
    fresh_seconds: float = ALIVE_FRESH_SECONDS,
) -> bool:
    if not alive_path:
        return False
    p = Path(alive_path)
    if not p.is_file():
        return False
    try:
        age = (time.time() if now is None else float(now)) - p.stat().st_mtime
    except OSError:
        return False
    return 0.0 <= age <= float(fresh_seconds)


def status_is_stale(
    snap_path: str | Path | None,
    *,
    engine_started_epoch: float,
    now: float | None = None,
    stale_seconds: float = STATUS_STALE_SECONDS,
) -> bool:
    """Match TrayStatusAge.IsStale including FR #7676 leftover grace."""
    epoch = time.time() if now is None else float(now)
    if engine_started_epoch <= 0:
        return False
    p = Path(snap_path) if snap_path else None
    if p is None or not p.is_file():
        return (epoch - engine_started_epoch) >= float(stale_seconds)
    try:
        written = p.stat().st_mtime
    except OSError:
        return False
    if written < engine_started_epoch:
        return (epoch - engine_started_epoch) >= float(stale_seconds)
    return (epoch - written) >= float(stale_seconds)


def evaluate_reason(
    snap_path: str | Path | None,
    alive_path: str | Path | None,
    *,
    engine_started_epoch: float,
    now: float | None = None,
    stale_seconds: float = STATUS_STALE_SECONDS,
) -> str:
    """Return '', 'starting-stuck', 'status-vs-alive', or 'status-stale'."""
    epoch = time.time() if now is None else float(now)
    if engine_started_epoch <= 0:
        return ""
    since_start = max(0.0, epoch - engine_started_epoch)
    label = read_short_or_title(snap_path)
    if is_starting_seed(label) and since_start >= STARTING_STUCK_SECONDS:
        return "starting-stuck"
    stale_after = max(
        float(stale_seconds),
        STATUS_WRITE_INTERVAL_SECONDS * STATUS_STALE_MULTIPLES,
    )
    if not status_is_stale(
        snap_path,
        engine_started_epoch=engine_started_epoch,
        now=epoch,
        stale_seconds=stale_after,
    ):
        return ""
    if alive_is_fresh(alive_path, now=epoch):
        return "status-vs-alive"
    return "status-stale"
