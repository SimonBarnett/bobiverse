"""Jeeves-owned shop registration registry (bobiverse).

Operators run ``!register <machine>``; Jeeves ChanServ-REGISTERs ``#{machine}``
and persists the set. Bob ears do not self-REGISTER shops.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REGISTRY_NAME = "registered-machines.json"

_SAFE_MID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$", re.I)


def registry_path(home: Path) -> Path:
    return Path(home) / REGISTRY_NAME


def normalize_machine_id(raw: str) -> str | None:
    s = (raw or "").strip().lstrip("#").lower()
    if not s or not _SAFE_MID.match(s):
        return None
    return s


def load_registered(home: Path) -> set[str]:
    p = registry_path(home)
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for item in data.get("machines") or []:
        mid = normalize_machine_id(str(item))
        if mid:
            out.add(mid)
    return out


def save_registered(home: Path, machines: set[str]) -> None:
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    payload = {
        "v": 1,
        "machines": sorted(machines),
    }
    registry_path(home).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
