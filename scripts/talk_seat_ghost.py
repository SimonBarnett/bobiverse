"""Watch-side ghost talk-seat prune: QUIT when home has no live irc_agent (issue #128 UNKNOWN 3)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import agent_control
import ergo_brief
import talk_seat_pid
from bobreport import normalize_machine_id

# Measured on live Ergo irc.ntsa.uk — updated from docs/evidence after P0 run.
# Worst-case Ergo idle-timeouts (90s ping + 150s disconnect) on irc.ntsa.uk.
ERGO_DEAD_TCP_NAMES_SEC = 240


def ergo_dead_tcp_names_s() -> float:
    raw = (os.environ.get("AGENTIC_IRC_ERGO_DEAD_TCP_S") or str(ERGO_DEAD_TCP_NAMES_SEC)).strip()
    try:
        n = float(raw)
    except ValueError:
        n = float(ERGO_DEAD_TCP_NAMES_SEC)
    return max(60.0, min(600.0, n))


def seat_recv_idle_s() -> float:
    """No server lines this long → talk seat QUIT (deaf / hung reader)."""
    raw = (os.environ.get("AGENTIC_IRC_SEAT_RECV_IDLE_S") or "150").strip()
    try:
        n = float(raw)
    except ValueError:
        n = 150.0
    cap = ergo_dead_tcp_names_s()
    return max(30.0, min(cap, n))


def pong_grace_s() -> float:
    raw = (os.environ.get("AGENTIC_IRC_PONG_GRACE_S") or "45").strip()
    try:
        n = float(raw)
    except ValueError:
        n = 45.0
    return max(5.0, min(120.0, n))


def discover_talk_seat_homes(machine_id: str) -> list[Path]:
    mid = normalize_machine_id(machine_id)
    if not mid:
        return []
    base = Path.home()
    candidates: list[Path] = []
    for pattern in (".agentic-irc-cursor", ".agentic-irc-cursor-*"):
        for path in sorted(base.glob(pattern)):
            if not path.is_dir():
                continue
            coord = path / "coordinator.pid"
            if not coord.is_file():
                continue
            try:
                doc = talk_seat_pid.parse_coordinator_pid(coord.read_text(encoding="utf-8"))
            except OSError:
                continue
            nick = (doc.get("nick") or "").strip()
            parsed = talk_seat_pid.parse_talk_seat_nick(nick)
            if parsed and parsed[0] == mid:
                candidates.append(path)
    return candidates


def ghost_prune_homes(
    machine_id: str,
    host: str,
    port: int,
    password: str,
    *,
    homes: list[Path] | None = None,
) -> list[str]:
    """Return nicks for which ghost QUIT was attempted (no live irc_agent on that home)."""
    out: list[str] = []
    for home in homes or discover_talk_seat_homes(machine_id):
        coord_path = home / "coordinator.pid"
        try:
            doc = talk_seat_pid.parse_coordinator_pid(coord_path.read_text(encoding="utf-8"))
        except OSError:
            continue
        nick = (doc.get("nick") or "").strip()
        if not nick or talk_seat_pid.parse_talk_seat_nick(nick) is None:
            continue
        if agent_control.find_irc_agent_pid(home) is not None:
            continue
        if ergo_brief.ghost_quit_session(host, port, nick, password):
            out.append(nick)
    return out


_prune_last = 0.0
_PRUNE_COOLDOWN_S = 45.0


def maybe_prune_local_ghosts(
    fleet_nick: str,
    host: str,
    port: int,
    password: str,
) -> list[str]:
    """Rate-limited entry for bob-* fleet agents (Watch-Bobiverse path)."""
    global _prune_last
    if not fleet_nick.lower().startswith("bob-"):
        return []
    mid = fleet_nick[4:]
    if not normalize_machine_id(mid):
        return []
    now = time.time()
    if now - _prune_last < _PRUNE_COOLDOWN_S:
        return []
    _prune_last = now
    return ghost_prune_homes(mid, host, port, password)
