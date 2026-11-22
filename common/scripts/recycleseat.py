"""FR #5059 / #5756: elevated tray recycle of a named worker seat.

``!recycleseat <nick> [machine]`` — ear authorises (+o/+h like !register, bob-* ear,
or fleet chair nick Jeeves even without NickServ account) and queues; tray (elevated
interactive session) stops the seat tree, verifies gone, then starts a fresh agent.
If stop fails, no new seat is started. Chair heals PRIVMSG the seat shop only
(never ``#bobiverse``); non-target ears stay silent before authorize.

Queue (mirrors startworker):
  <install>\\run\\recycleseat\\req-<id>.json  {id, nick, by, kind, ts, expires}
  <install>\\run\\recycleseat\\res-<id>.json  {id, ok, reason, old_pid, new_pid}
Tray/engine alive stamps are shared with ``run\\startworker`` (same interactive session).
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import startworker as sw
import unregister_cmd
import bobreport

CMD = "!recycleseat"
REQUEST_TTL_S = 300.0  # FR #8864: tray tick can lag past 60s; keep the req until the queue runs
ACK_COOLDOWN_S = 900.0
# FR #8602: stale doing / accepted_silent may --force past the busy gate.
DEFAULT_STUCK_S = 900.0
QUEUE_SUBDIR = ("run", "recycleseat")
DISABLE_FILE = "recycleseat.disabled"
_NICK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
_JUNK = {c: None for c in range(0, 32)}
_STUCK_MARKERS = ("accepted_silent", "lost_ack_restart", "lost_ack", "opencode-lost-ack", "opencode-frozen")


def stuck_threshold_s(env: dict | None = None) -> float:
    """Seconds of stale worker.updated before --force may override busy (FR #8602)."""
    src = env if env is not None else os.environ
    for key in ("BOB_RECYCLESEAT_STUCK_S", "BOB_WORKER_OPENCODE_FROZEN_PROGRESS_S"):
        raw = str(src.get(key) or "").strip()
        if not raw:
            continue
        try:
            return max(60.0, float(raw))
        except ValueError:
            continue
    return DEFAULT_STUCK_S


def parse(body: str):
    """``!recycleseat <nick> [machine] [--force]`` -> (nick, machine|None, force) | 'usage' | None.

    FR #8602: optional ``--force`` lets ops recycle a stuck busy seat (stale
    ``worker.updated`` or ``accepted_silent``). Fresh busy seats still NACK.
    """
    text = str(body or "").translate(_JUNK).strip().lstrip(":").strip()
    if not text:
        return None
    parts = text.split()
    if not parts or parts[0].lower() != CMD:
        return None
    force = False
    if len(parts) >= 2 and parts[-1].lower() in ("--force", "-force", "force"):
        force = True
        parts = parts[:-1]
    if len(parts) < 2 or len(parts) > 3:
        return "usage"
    nick = parts[1]
    if not _NICK_RE.match(nick):
        return "usage"
    machine = None
    if len(parts) == 3:
        tok = parts[2]
        if not sw._MACHINE_RE.match(tok):
            return "usage"
        machine = tok.lower().lstrip("#")
    return (nick, machine, force)


def usage() -> str:
    return (
        "usage: !recycleseat <nick> [machine] [--force]   "
        "(machine required in #bobiverse; --force only when stuck)"
    )


def authorize(
    nick: str,
    account,
    *,
    channel: str,
    machine_of_nick: Callable[[str], str | None],
    member_lookup: Callable[[str, str], set[str]] | None = None,
    members: dict | None = None,
    chair_nicks: Iterable[str] = ("jeeves",),
    owners: set | None = None,
):
    """-> (ok, kind, reason).

    FR #5059: same live IRC op check as !register (+o/+h), plus verified bob-* ear.
    FR #5756: live +o/+h and fleet chair nick (Jeeves) authorize even without a
    NickServ account — otherwise chair !recycleseat is always unverified.
    """
    n = str(nick or "").strip()
    low = n.lower()
    acct = str(account or "").strip().lower()
    # Live channel op/halfop (FR #4008 / !register) — before account gate (FR #5756).
    if unregister_cmd.nick_has_op_or_halfop(
        nick=n, channel=channel or "#bobiverse", members=members, member_lookup=member_lookup
    ):
        return True, "op", ""
    # Fleet chair nick (Jeeves) may lack services account on Ergo (FR #5756).
    if low in {c.lower() for c in chair_nicks}:
        return True, "chair", ""
    if not acct:
        return False, "", "unverified"
    same = acct in (low, low.rstrip("_"))
    if same and low.startswith("bob-") and machine_of_nick(n):
        return True, "ear", ""
    # Verified owner account (Simon) — fleet operator even if MODE lag.
    if acct in (owners if owners is not None else sw.owner_accounts()):
        return True, "owner", ""
    return False, "", "denied"


def queue_dir(install_root) -> Path:
    return Path(install_root).joinpath(*QUEUE_SUBDIR)


def alive_dir(install_root) -> Path:
    """Share startworker tray/engine heartbeats (same interactive tray process)."""
    return sw.queue_dir(install_root)


def write_request(qdir, seat_nick: str, by: str, kind: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    rid = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now)) + "-" + uuid.uuid4().hex[:6]
    d = Path(qdir)
    d.mkdir(parents=True, exist_ok=True)
    body = {
        "id": rid,
        "nick": seat_nick,
        "by": by,
        "kind": kind,
        "ts": int(now),
        "expires": int(now + REQUEST_TTL_S),
    }
    tmp = d / f".req-{rid}.tmp"
    ack = d / f"ack-{seat_nick.lower()}.json"
    ack_tmp = d / f".ack-{rid}.tmp"
    try:
        tmp.write_text(json.dumps(body), encoding="utf-8")
        ack_tmp.write_text(json.dumps({"ts": now}), encoding="utf-8")
        os.replace(ack_tmp, ack)
        try:
            os.replace(tmp, d / f"req-{rid}.json")
        except OSError:
            ack.unlink(missing_ok=True)
            raise
    finally:
        tmp.unlink(missing_ok=True)
        ack_tmp.unlink(missing_ok=True)
    return rid


RECYCLE_LIVE_SCRIPTS = (
    "bob/tray/tools/BobTrayRecycleSeat.ps1",
    "common/scripts/recycleseat.py",
    "common/scripts/gitclaim.py",
)


def dirty_recycle_script_paths(names) -> list[str]:
    """Tracked paths that must not stay dirty on a live install (FR #7117)."""
    want = {p.replace("\\", "/").lower() for p in RECYCLE_LIVE_SCRIPTS}
    out: list[str] = []
    for raw in names or []:
        n = str(raw or "").replace("\\", "/").lstrip("./")
        if n.lower() in want:
            out.append(n.replace("\\", "/"))
    return out


def _digest_read_candidates(home, install_root=None) -> list[Path]:
    """SYSTEM-readable digest homes: ear home, BOB_DIGEST_HOME, install home, ProgramData."""
    seen: set[str] = set()
    cands: list[Path] = []

    def _add(p) -> None:
        if p is None:
            return
        try:
            key = str(Path(p).resolve())
        except OSError:
            key = str(p)
        if key in seen:
            return
        seen.add(key)
        cands.append(Path(p))

    if home is not None:
        _add(bobreport.fleet_digest_home(Path(home)))
    envh = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    if envh:
        _add(envh)
    if install_root:
        ir = Path(install_root)
        _add(ir / "home")
        _add(ir)
    pd = (os.environ.get("ProgramData") or "").strip()
    if pd:
        _add(Path(pd) / "bobiverse")
    return cands


def _worker_row_is_busy(worker: dict) -> bool:
    """True when a digest worker row shows in-progress work (list or map shape)."""
    if not isinstance(worker, dict):
        return False
    if str(worker.get("working_on") or "").strip():
        return True
    if str(worker.get("work") or "").strip():
        return True
    return str(worker.get("state") or "").lower() in ("doing", "busy", "accepted")


def _worker_row_stuck(worker: dict, *, now: float, threshold_s: float | None = None) -> bool:
    """FR #8602: stuck when accepted_silent/LOST_ACK stamped or worker.updated is stale."""
    if not isinstance(worker, dict):
        return False
    blob = " ".join(
        str(worker.get(k) or "")
        for k in ("state", "work", "working_on", "stuck_reason", "reason", "hang", "note")
    ).lower()
    if any(m in blob for m in _STUCK_MARKERS):
        return True
    thr = float(threshold_s) if threshold_s is not None else stuck_threshold_s()
    for key in ("updated", "updated_at", "last_progress"):
        ts = bobreport._parse_worker_updated_ts(worker.get(key))
        if ts is None:
            continue
        if (float(now) - float(ts)) >= thr:
            return True
    return False


def _seat_rows_from_doc(doc: dict, seat_nick: str) -> list[dict]:
    """Collect digest rows matching seat_nick (map + list shapes)."""
    legacy = bobreport.parse_worker_nick(seat_nick.lower())
    mid, _, pid = seat_nick.lower().rpartition("-")
    if legacy:
        mid, pid = legacy
    if not mid or not pid.isdigit():
        return []
    mid = bobreport.fold_machine_id(mid)
    ent = (doc.get("machines") or {}).get(mid) or {}
    if not isinstance(ent, dict):
        return []
    rows: list[dict] = []
    workers = ent.get("workers")
    if isinstance(workers, dict):
        row = workers.get(str(int(pid))) or workers.get(seat_nick.lower()) or workers.get(seat_nick)
        if isinstance(row, dict):
            rows.append(row)
    elif isinstance(workers, list):
        for worker in workers:
            if isinstance(worker, dict) and str(worker.get("nick") or "").strip().lower() == seat_nick.lower():
                rows.append(worker)
    for worker in ent.get("worker_list") or []:
        if isinstance(worker, dict) and str(worker.get("nick") or "").strip().lower() == seat_nick.lower():
            rows.append(worker)
    return rows


def _work_from_doc(doc: dict, seat_nick: str) -> bool:
    """FR #7149: accept list-shaped machines.<mid>.workers (live digest) as well as pid maps."""
    return any(_worker_row_is_busy(row) for row in _seat_rows_from_doc(doc, seat_nick))


def _stuck_from_doc(doc: dict, seat_nick: str, *, now: float) -> bool:
    """True when any matching busy row looks stuck (FR #8602)."""
    thr = stuck_threshold_s()
    return any(
        _worker_row_is_busy(row) and _worker_row_stuck(row, now=now, threshold_s=thr)
        for row in _seat_rows_from_doc(doc, seat_nick)
    )


def _load_digest_doc(home, install_root=None) -> tuple[dict | None, str]:
    """Return (doc, err). doc None + empty err means no digest yet; err set means unreadable."""
    if home is None and not install_root:
        return None, ""
    last_err = ""
    any_path = False
    for base in _digest_read_candidates(home, install_root):
        path = bobreport.digest_path(base)
        any_path = True
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError) as e:
            last_err = f"{type(e).__name__}"
            continue
        try:
            doc = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            return None, type(e).__name__
        if not isinstance(doc, dict):
            return None, "TypeError"
        return doc, ""
    if last_err:
        return None, last_err
    if not any_path:
        return None, ""
    return None, ""


def inspect_seat_work(home, seat_nick: str, install_root=None) -> tuple[bool, bool, str]:
    """(known, working, error). Never raises. FR #7117: retry SYSTEM-readable digest homes."""
    doc, err = _load_digest_doc(home, install_root)
    if err:
        return False, False, err
    if doc is None:
        return True, False, ""
    try:
        return True, bool(_work_from_doc(doc, seat_nick)), ""
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return False, False, type(e).__name__


def inspect_seat_stuck(
    home, seat_nick: str, install_root=None, *, now: float | None = None
) -> bool:
    """FR #8602: True when busy seat looks stuck (stale updated / accepted_silent)."""
    doc, err = _load_digest_doc(home, install_root)
    if err or doc is None:
        return False
    try:
        return bool(_stuck_from_doc(doc, seat_nick, now=time.time() if now is None else now))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def seat_is_working(home, seat_nick: str, install_root=None) -> bool:
    """Read seat-specific work without healing or clearing any digest evidence."""
    known, working, _err = inspect_seat_work(home, seat_nick, install_root)
    if not known:
        raise OSError(_err or "state_unavailable")
    return working


def ack_cooldown_left(qdir, seat_nick: str, now: float) -> float:
    path = Path(qdir) / f"ack-{seat_nick.lower()}.json"
    try:
        last = float(json.loads(path.read_text(encoding="utf-8"))["ts"])
    except FileNotFoundError:
        return 0.0
    if not math.isfinite(last):
        raise ValueError("invalid ACK timestamp")
    return max(0.0, ACK_COOLDOWN_S - (now - last))


@dataclass
class Decision:
    ok: bool
    reason: str
    line: str
    kind: str = ""
    request_id: str = ""
    seat_nick: str = ""


def decide(
    *,
    body: str,
    nick: str,
    account,
    channel: str,
    local_machine: str,
    qdir,
    install_root,
    home=None,
    machine_of_nick: Callable[[str], str | None],
    member_lookup: Callable[[str, str], set[str]] | None = None,
    members: dict | None = None,
    chair_nicks=("jeeves",),
    owners: set | None = None,
    now: float | None = None,
    write: bool = True,
    debug: Callable[[str], None] | None = None,
) -> Decision | None:
    """None when body is not !recycleseat; else ACK/NACK (request queued on ok)."""
    parsed = parse(body)
    if parsed is None:
        return None
    now = time.time() if now is None else now
    nack = lambda reason, text, **kw: Decision(  # noqa: E731
        False, reason, f"NACK recycleseat: {text}", **kw
    )
    if parsed == "usage":
        return nack("usage", usage())
    seat_nick, machine, force = parsed
    local = (local_machine or "").strip().lower()
    chan = (channel or "").strip().lower().lstrip("#")
    # FR #5756: non-target ears stay silent BEFORE authorize (no public NACK flood).
    if machine is not None and local and machine != local:
        if debug is not None:
            debug(f"recycleseat ignore seat={seat_nick} machine={machine} local={local}: other machine")
        return None
    ok, kind, why = authorize(
        nick,
        account,
        channel=channel or "#bobiverse",
        machine_of_nick=machine_of_nick,
        member_lookup=member_lookup,
        members=members,
        chair_nicks=chair_nicks,
        owners=owners,
    )
    if not ok:
        return nack(
            why,
            "not verified (log in to your services account)"
            if why == "unverified"
            else "denied (+o/+h, bob-* ear, Jeeves or owner only)",
            seat_nick=seat_nick,
        )
    if not local:
        return nack("no_machine", "this ear has no machine id", kind=kind, seat_nick=seat_nick)
    if machine is None:
        if chan != local:
            return nack(
                "machine_required",
                "name the machine: !recycleseat <nick> " + local,
                kind=kind,
                seat_nick=seat_nick,
            )
        machine = local
    if machine != local:
        return None  # other ear: silent
    if chan not in (local, "bobiverse") and channel:
        return nack(
            "wrong_channel",
            f"use #{local} or #bobiverse",
            kind=kind,
            seat_nick=seat_nick,
        )
    if home is not None and (
        (Path(home) / DISABLE_FILE).exists() or os.environ.get("BOB_RECYCLESEAT_DISABLE")
    ):
        return nack(
            "disabled",
            "remote seat recycle is disabled on this machine",
            kind=kind,
            seat_nick=seat_nick,
        )
    known, working, inspect_err = inspect_seat_work(home, seat_nick, install_root)
    if not known:
        why = inspect_err or "unknown"
        return nack(
            "state_unavailable",
            f"cannot verify current working_on for {seat_nick} ({why})",
            kind=kind,
            seat_nick=seat_nick,
        )
    if working:
        # FR #8602: --force only when stuck (stale updated / accepted_silent).
        stuck = inspect_seat_stuck(home, seat_nick, install_root, now=now)
        if force and stuck:
            if debug is not None:
                debug(f"recycleseat force-stuck seat={seat_nick}")
        elif force and not stuck:
            return nack(
                "busy",
                f"busy {seat_nick}: --force refused (not stuck; updated fresh or no accepted_silent)",
                kind=kind,
                seat_nick=seat_nick,
            )
        else:
            return nack(
                "busy",
                f"busy {seat_nick}: current working_on; hand back (GIVEUP) before recycle"
                + ("; or --force when stuck" if stuck else ""),
                kind=kind,
                seat_nick=seat_nick,
            )
    try:
        left = ack_cooldown_left(qdir, seat_nick, now)
    except (OSError, ValueError, TypeError, KeyError):
        return nack(
            "queue_error",
            f"could not read recycle ACK cooldown for {seat_nick}",
            kind=kind,
            seat_nick=seat_nick,
        )
    if left > 0:
        return nack(
            "busy",
            f"busy {seat_nick}: recycle ACK cooldown {math.ceil(left)}s",
            kind=kind,
            seat_nick=seat_nick,
        )
    adir = alive_dir(install_root)
    if not sw.tray_alive(adir, now):
        return nack(
            "no_interactive_session",
            "nobody is logged in with the Bob tray running",
            kind=kind,
            seat_nick=seat_nick,
        )
    if not sw.engine_alive(adir, now):
        return nack(
            "engine_stale",
            "Bob tray engine is not ticking; restart the tray",
            kind=kind,
            seat_nick=seat_nick,
        )
    rid = ""
    if write:
        try:
            rid = write_request(qdir, seat_nick, nick, kind, now)
        except OSError as e:
            return nack(
                "queue_error",
                f"could not queue the request ({type(e).__name__})",
                kind=kind,
                seat_nick=seat_nick,
            )
    return Decision(
        True,
        "ok",
        f"ACK recycleseat {seat_nick} on {local} (queued {rid or '-'}; by {nick})",
        kind=kind,
        request_id=rid,
        seat_nick=seat_nick,
    )


# --------------------------------------------------------------------------- tray policy (pure; PS mirrors)

def pid_from_seat_nick(nick: str) -> int:
    """FR #6986: ``<machine>-<pid>`` seat nicks encode the worker pid.

    Tray recycle used only ``%LOCALAPPDATA%\\...\\seats\\<nick>.irc.json``. When
    that marker was missing, recycle was ``not-found`` and the live pid survived
    (same nick, bored lag kept growing).
    """
    n = str(nick or "").strip()
    if "-" not in n:
        return 0
    rest = n.rsplit("-", 1)[-1]
    if rest.isdigit() and int(rest) > 0:
        return int(rest)
    return 0


def resolve_recycle_pid(marker_pid: int, nick: str) -> int:
    """Prefer the IRC seat marker pid; fall back to the nick suffix."""
    try:
        mp = int(marker_pid or 0)
    except (TypeError, ValueError):
        mp = 0
    if mp > 0:
        return mp
    return pid_from_seat_nick(nick)


def plan_recycle_action(
    *,
    stop_ok: bool,
    target_still_alive: bool,
    target_found: bool,
    expired: bool = False,
) -> tuple[bool, str]:
    """Return (may_start, reason). CAST IRON: never start if stop failed / still alive."""
    if expired:
        return False, "expired"
    if not target_found:
        return False, "not-found"
    if not stop_ok:
        return False, "stop-failed"
    if target_still_alive:
        return False, "still-alive"
    return True, "ok"
