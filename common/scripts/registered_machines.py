"""Jeeves-owned shop registry (bobiverse): a MIRROR of ChanServ-registered machine channels.

The chair (an Ergo oper) periodically asks ``ChanServ LIST`` for every registered channel
and mirrors the machine channels (``#<machinename>``, never ``#bobiverse``) into
``registered-machines.json``: newly registered channels are ADDED and channels no longer
registered are REMOVED. The file is a persisted cache - a ChanServ outage / denied / garbled
reply keeps the last good list. ``!register <machine>`` still works (ChanServ REGISTER +
immediate add + a forced re-sync). Bob ears do not self-REGISTER shops via this file.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_NAME = "registered-machines.json"
SOURCE_CHANSERV = "chanserv-list"
SOURCE_REGISTER = "register-command"

# Registered channels that are NOT machine shops. Anything with a character outside
# [a-z0-9-] (e.g. #agentic_irc) is excluded by the id check below.
# FR #3834: #wonderland is the shared airc client fallback (not a machine shop).
NON_MACHINE_CHANNELS = frozenset({"bobiverse", "wonderland"})
EXCLUDE_ENV = "BOB_CHANSERV_EXCLUDE"  # extra comma-separated channel names to ignore

_SAFE_MID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$", re.I)
_IRC_FMT = re.compile(r"[\x00-\x1f\x7f]|\x03\d{0,2}(,\d{1,2})?")


def registry_path(home: Path) -> Path:
    return Path(home) / REGISTRY_NAME


def normalize_machine_id(raw: str) -> str | None:
    s = (raw or "").strip().lstrip("#").lower()
    if not s or not _SAFE_MID.match(s):
        return None
    return s


def _read_doc(home: Path) -> dict:
    p = registry_path(home)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_registered(home: Path) -> set[str]:
    out: set[str] = set()
    for item in _read_doc(home).get("machines") or []:
        mid = normalize_machine_id(str(item))
        if mid:
            out.add(mid)
    return out


def registry_meta(home: Path) -> dict:
    """``{source, refreshed_at, refreshed_ts}`` of the persisted ChanServ mirror ({} if none)."""
    doc = _read_doc(home)
    out: dict = {}
    for key in ("source", "refreshed_at"):
        if doc.get(key):
            out[key] = str(doc[key])
    try:
        if doc.get("refreshed_ts") is not None:
            out["refreshed_ts"] = float(doc["refreshed_ts"])
    except (TypeError, ValueError):
        pass
    return out


def registry_age_s(home: Path, now: float | None = None) -> float | None:
    """Seconds since the last SUCCESSFUL ChanServ sync; None if never synced."""
    ts = registry_meta(home).get("refreshed_ts")
    if ts is None:
        return None
    return max(0.0, (time.time() if now is None else now) - ts)


def refresh_due(home: Path, ttl_s: float, now: float | None = None) -> bool:
    age = registry_age_s(home, now)
    return age is None or age >= ttl_s


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:10]}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        last: OSError | None = None
        for delay in (0.0, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8):
            if delay:
                time.sleep(delay)
            try:
                os.replace(tmp, path)
                return
            except PermissionError as exc:  # WinError 5 / 32
                last = exc
        if last:
            raise last
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def save_registered(
    home: Path,
    machines: set[str],
    *,
    source: str | None = None,
    refreshed_at: float | None = None,
) -> None:
    """Persist the set. ``refreshed_at`` (epoch) is only passed by a successful ChanServ sync."""
    home = Path(home)
    prev = _read_doc(home)
    payload: dict = {"v": 2, "machines": sorted(machines)}
    payload["source"] = source or prev.get("source") or SOURCE_REGISTER
    if refreshed_at is not None:
        payload["refreshed_ts"] = float(refreshed_at)
        payload["refreshed_at"] = datetime.fromtimestamp(refreshed_at, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    else:
        for key in ("refreshed_ts", "refreshed_at"):
            if prev.get(key) is not None:
                payload[key] = prev[key]
    _atomic_write(registry_path(home), json.dumps(payload, indent=2) + "\n")


def add_registered(home: Path, machine: str) -> str | None:
    mid = normalize_machine_id(machine)
    if not mid:
        return None
    cur = load_registered(home)
    cur.add(mid)
    save_registered(home, cur)
    return mid


def is_registered(home: Path, machine: str) -> bool:
    mid = normalize_machine_id(machine)
    return bool(mid and mid in load_registered(home))


def _excluded_names() -> set[str]:
    extra = {
        p.strip().lstrip("#").lower()
        for p in (os.environ.get(EXCLUDE_ENV) or "").split(",")
        if p.strip()
    }
    return set(NON_MACHINE_CHANNELS) | extra


def machine_ids_from_channels(channels) -> set[str]:
    """Machine ids for registered channels ``#<machinename>`` (not #bobiverse / non-machine)."""
    skip = _excluded_names()
    out: set[str] = set()
    for ch in channels or []:
        raw = str(ch or "").strip()
        if not raw.startswith("#") or raw.startswith("##"):
            continue
        name = raw[1:].lower()
        if name in skip:
            continue
        mid = normalize_machine_id(name)
        if mid and mid not in skip:
            out.add(mid)
    return out


class ChanServListCollector:
    """Parse the NOTICE stream of ``ChanServ LIST`` (Ergo ``irc/chanserv.go csListHandler``).

    Ergo replies ``*** ChanServ LIST ***``, one NOTICE per channel (leading spaces), then
    ``*** End of ChanServ LIST ***``. A permission error ("Insufficient privileges" /
    "Command restricted" ...) or a missing end marker is a FAILED query, never an empty list.
    """

    _DENIED = re.compile(r"(?i)(insufficient|restricted|denied|not permitted|unknown command|"
                         r"must be (an )?oper|no such command|permission)")

    def __init__(self) -> None:
        self.started = False
        self.done = False
        self.failed = False
        self.error = ""
        self.channels: list[str] = []

    @staticmethod
    def clean(text: str) -> str:
        return _IRC_FMT.sub("", text or "").strip()

    def feed(self, text: str) -> str | None:
        """Feed one ChanServ NOTICE body. Returns 'start'|'chan'|'end'|'error'|None."""
        if self.done or self.failed:
            return None
        t = self.clean(text)
        low = t.lower()
        if low.startswith("***") and "chanserv list" in low:
            if "end of" in low:
                if not self.started:
                    return None
                self.done = True
                return "end"
            self.started = True
            self.channels = []
            return "start"
        if not self.started:
            if self._DENIED.search(t):
                self.failed = True
                self.error = t[:120]
                return "error"
            return None
        if t.startswith("#"):
            self.channels.append(t.split()[0])
            return "chan"
        return None


def sync_from_chanserv(
    home: Path, channels, *, now: float | None = None, allow_empty: bool = False
) -> tuple[set[str], set[str]] | None:
    """Mirror a COMPLETE ChanServ LIST into the registry. Returns ``(added, removed)``.

    ``None`` = rejected, last good list kept: a result with zero machine channels is treated as
    a bad query (an oper losing ``chanreg`` must not wipe the roster) unless ``allow_empty``.
    """
    ids = machine_ids_from_channels(channels)
    if not ids and not allow_empty:
        return None
    cur = load_registered(home)
    added, removed = ids - cur, cur - ids
    save_registered(
        Path(home), ids, source=SOURCE_CHANSERV, refreshed_at=time.time() if now is None else now
    )
    return added, removed


def parse_register_command(body: str) -> str | None:
    """Return machine id if body is ``!register <machine>``, else None."""
    text = (body or "").strip()
    m = re.match(r"^!register\s+(\S+)\s*$", text, re.I)
    if not m:
        return None
    return normalize_machine_id(m.group(1))


def bob_nick_for_machine(machine: str) -> str:
    mid = normalize_machine_id(machine) or (machine or "").strip()
    return f"Bob-{mid}"


def machine_from_bob_nick(nick: str) -> str | None:
    n = (nick or "").strip().rstrip("_")
    m = re.match(r"^bob-(.+)$", n, re.I)
    if not m:
        return None
    return normalize_machine_id(m.group(1))