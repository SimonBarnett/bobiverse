"""Talk-seat identity: IRC nick {machine-id}-{pid} uses python irc_agent PID (never irc_listen)."""
from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from bobreport import normalize_machine_id, seat_machine_ids

_COORD_LINE = re.compile(r"^([a-z_]+)=(.*)$", re.IGNORECASE)
_SEAT_ENV = "BOB_IRC_SEAT_PID"


def parse_talk_seat_nick(nick: str) -> tuple[str, str] | None:
    """Return (machine_id, pid_str) for fleet talk-seat nicks, else None."""
    n = (nick or "").strip().lower()
    if not n or n.startswith("bob-") or n.startswith("w-"):
        return None
    # #39 gap 1: registered (ChanServ) machines are seats too, not just the bootstrap four.
    for mid in seat_machine_ids():
        prefix = f"{mid}-"
        if not n.startswith(prefix):
            continue
        pid_s = n[len(prefix) :]
        if pid_s.isdigit() and int(pid_s) > 0:
            norm = normalize_machine_id(mid)
            if norm:
                return norm, pid_s
    return None


def talk_seat_nick(machine_id: str, pid: int | str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return f"{mid}-{int(pid)}"


def nick_suffix_pid(nick: str) -> str | None:
    parsed = parse_talk_seat_nick(nick)
    return parsed[1] if parsed else None


def validate_nick_seat_pid(nick: str, seat_pid: int | str) -> bool:
    suffix = nick_suffix_pid(nick)
    if suffix is None:
        return True
    try:
        return int(suffix) == int(seat_pid)
    except (TypeError, ValueError):
        return False


def check_nick_seat_pid(nick: str, seat_pid: int | str) -> str | None:
    """None if OK; else human-readable INFO line (no newline)."""
    suffix = nick_suffix_pid(nick)
    if suffix is None:
        return None
    try:
        want = int(seat_pid)
        have = int(suffix)
    except (TypeError, ValueError):
        return "INFO talk-seat nick suffix is not a valid pid"
    if have != want:
        return (
            f"INFO talk-seat nick suffix {have} != irc_agent PID {want} "
            "(must not use irc_listen PID or PowerShell seat host PID)"
        )
    return None


def parse_coordinator_pid(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _COORD_LINE.match(line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def _agent_pid_from_doc(doc: dict[str, str]) -> int | None:
    """Authoritative talk-seat PID: agent= then seat= (legacy alias)."""
    raw = (doc.get("agent") or doc.get("seat") or doc.get("host") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _seat_pid_from_doc(doc: dict[str, str]) -> int | None:
    return _agent_pid_from_doc(doc)


def coordinator_seat_pid(home: Path | str) -> int | None:
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return _seat_pid_from_doc(doc)


def watch_seat_host_ok(nick: str, home: Path | str | None, alive=None) -> bool:
    """AgentMonitor watch seats name the nick after the live monitor PID (coordinator seat=).

    Since #119 agent= (irc_agent PID) is authoritative, but Watch-AgentHealth writes
    agent=<irc_agent> AFTER launch, so every irc_agent restart saw suffix != agent= and
    exited (crash loop, MarchHare 2026-09-25 11:28 BST). Accept the nick when its suffix
    equals coordinator seat= AND that seat process is alive.
    """
    suffix = nick_suffix_pid(nick)
    if suffix is None or not home:
        return False
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return False
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
        seat = int((doc.get("seat") or "").strip())
        have = int(suffix)
    except (OSError, ValueError):
        return False
    if seat != have or seat <= 0:
        return False
    if alive is None:
        alive = _pid_alive
    return bool(alive(seat))


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        h = k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def seat_pid_from_env() -> int | None:
    raw = (os.environ.get(_SEAT_ENV) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def resolve_seat_pid(
    home: Path | str | None = None, *, self_pid: int | None = None
) -> int | None:
    """irc_agent PID: env BOB_IRC_SEAT_PID (or self), then coordinator.pid agent=."""
    raw = (os.environ.get(_SEAT_ENV) or "").strip()
    if raw.lower() == "self":
        if self_pid is not None and self_pid > 0:
            return int(self_pid)
        return None
    pid = seat_pid_from_env()
    if pid is not None:
        return pid
    if home:
        return coordinator_seat_pid(home)
    return None


def check_coordinator_nick(home: Path | str) -> str | None:
    """Validate coordinator.pid nick suffix matches authoritative agent= / seat= line."""
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    nick = (doc.get("nick") or "").strip()
    seat = _seat_pid_from_doc(doc)
    if not nick or seat is None:
        return None
    return check_nick_seat_pid(nick, seat)


def parse_talk_seat_placeholder(nick: str) -> str | None:
    """Return machine_id for start placeholder ``{machine}-0``, else None.

    FR #120 / A3: Start-TalkSeat passes ``--nick {mid}-0 --auto-nick``. Suffix 0 is
    not a talk-seat pid (``parse_talk_seat_nick`` requires pid > 0), so rewrite
    must special-case the placeholder.
    """
    n = (nick or "").strip().lower()
    if not n or n.startswith("bob-") or n.startswith("w-"):
        return None
    for mid in seat_machine_ids():
        if n == f"{mid}-0":
            norm = normalize_machine_id(mid)
            return norm or None
    return None


def auto_talk_seat_nick(nick: str, seat_pid: int) -> str:
    """If nick is a talk-seat (or ``{machine}-0`` placeholder), rewrite suffix to seat_pid."""
    try:
        pid = int(seat_pid)
    except (TypeError, ValueError):
        return nick
    if pid <= 0:
        return nick
    mid = parse_talk_seat_placeholder(nick)
    if mid:
        return talk_seat_nick(mid, pid)
    parsed = parse_talk_seat_nick(nick)
    if not parsed:
        return nick
    mid, _ = parsed
    return talk_seat_nick(mid, pid)


def home_bind_refusal(
    coord: dict[str, str],
    expected_nick: str,
    *,
    live_agent_nick: str | None = None,
    has_live_listen: bool = False,
) -> str | None:
    """None if Start-TalkSeat may bind; else a one-line refusal (no secrets)."""
    expected = (expected_nick or "").strip()
    if not expected:
        return "expected talk-seat nick is required"
    lock_nick = (coord.get("nick") or "").strip()
    lock_seat = (coord.get("seat") or "").strip()
    agent_nick = (live_agent_nick or "").strip()
    occupied = bool(agent_nick) or has_live_listen

    if agent_nick and agent_nick != expected:
        if lock_nick == expected:
            return None
        seat_part = f" seat={lock_seat}" if lock_seat else ""
        return (
            f"home has live irc_agent nick={agent_nick}{seat_part}; "
            f"this seat wants {expected}. Use a different -IrcHome "
            "(e.g. ~/.bobiverse-cursor-2). Do not kill the other seat's listen."
        )

    if lock_nick and lock_nick != expected and occupied:
        seat_part = f" seat={lock_seat}" if lock_seat else ""
        return (
            f"coordinator.pid nick={lock_nick}{seat_part} with live listen/agent; "
            f"this seat wants {expected}. Use a different -IrcHome "
            "(e.g. ~/.bobiverse-cursor-2). Do not steal the first talk-seat home."
        )
    return None


def process_is_alive(pid: int) -> bool:
    """True when OS process pid is still running."""
    try:
        n = int(pid)
    except (TypeError, ValueError):
        return False
    if n <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, n)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(n, 0)
    except OSError:
        return False
    return True


def seat_liveness_poll_s() -> float:
    raw = (os.environ.get("BOB_IRC_SEAT_LIVENESS_S") or "15").strip()
    try:
        n = float(raw)
    except ValueError:
        n = 15.0
    return max(3.0, min(120.0, n))


def seat_liveness_disabled() -> bool:
    return (os.environ.get("BOB_IRC_SEAT_LIVENESS") or "").strip().lower() in (
        "0",
        "off",
        "false",
        "no",
    )


def talk_seat_monitor_pid(nick: str, home: Path | str) -> int | None:
    """PowerShell seat PID for a talk-seat nick (coordinator.pid when readable, else nick suffix)."""
    parsed = parse_talk_seat_nick(nick)
    if not parsed:
        return None
    try:
        suffix_pid = int(parsed[1])
    except (TypeError, ValueError):
        return None
    from_file = coordinator_seat_pid(home)
    if from_file is not None:
        return from_file
    return suffix_pid


def talk_seat_coordinator_gone(
    nick: str,
    home: Path | str,
    *,
    is_alive: Callable[[int], bool] | None = None,
) -> bool:
    """True when the talk-seat coordinator process is not running."""
    alive = is_alive or process_is_alive
    pid = talk_seat_monitor_pid(nick, home)
    if pid is None:
        return False
    return not alive(pid)


def coordinator_looks_like_monitor(pid: int, command_line: str | None = None) -> bool:
    """FR #238: True when coordinator CL looks like Watch-AgentHealth / seat monitor.

    Used only for a one-shot warning when IRC was started outside the monitor.
    """
    cl = (command_line or "").lower()
    if not cl:
        return True  # unknown CL — do not warn
    markers = (
        "watch-agenthealth",
        "watch-agent-health",
        "start-bobwatchworker",
        "agentmonitor",
    )
    return any(m in cl.replace("\\", "/") for m in markers)


def warn_if_coordinator_not_monitor(
    home: Path | str,
    *,
    command_line_for_pid: Callable[[int], str | None] | None = None,
) -> str | None:
    """Return a warning string when seat= PID does not look like a monitor."""
    path = Path(home) / "coordinator.pid"
    if not path.is_file():
        return None
    try:
        doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
        seat = int((doc.get("seat") or "").strip() or "0")
    except (OSError, ValueError):
        return None
    if seat <= 0:
        return None
    getter = command_line_for_pid
    cl = getter(seat) if getter else _command_line_for_pid(seat)
    if coordinator_looks_like_monitor(seat, cl):
        return None
    return (
        f"coordinator seat={seat} does not look like Watch-AgentHealth "
        f"(cl={(cl or '')[:120]!r}); IRC may outlive the seat — prefer monitor irc ensure "
        "or scripts/Start-IrcPair.ps1 -CoordinatorPid <monitorPid>"
    )


def _command_line_for_pid(pid: int) -> str | None:
    if os.name != "nt" or pid <= 0:
        return None
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\").CommandLine",
            ],
            text=True,
            timeout=15,
        )
        return (out or "").strip() or None
    except Exception:
        return None


def check_home_bind(
    home: Path | str,
    expected_nick: str,
    *,
    live_agent_nick: str | None = None,
    has_live_listen: bool = False,
) -> str | None:
    path = Path(home) / "coordinator.pid"
    doc: dict[str, str] = {}
    if path.is_file():
        try:
            doc = parse_coordinator_pid(path.read_text(encoding="utf-8"))
        except OSError:
            doc = {}
    return home_bind_refusal(
        doc,
        expected_nick,
        live_agent_nick=live_agent_nick,
        has_live_listen=has_live_listen,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Talk-seat nick / coordinator.pid guard")
    p.add_argument("--home", default="", help="check coordinator.pid under this home")
    p.add_argument("--nick", default="")
    p.add_argument("--pid", type=int, default=0)
    p.add_argument(
        "--bind-home",
        action="store_true",
        help="refuse binding a home owned by another talk seat (exit 3)",
    )
    p.add_argument("--expected-nick", default="")
    p.add_argument("--live-agent-nick", default="")
    p.add_argument(
        "--live-listen",
        action="store_true",
        help="irc_listen is running for this home",
    )
    args = p.parse_args(argv)
    if args.bind_home:
        if not args.home or not args.expected_nick:
            print("INFO pass --home and --expected-nick with --bind-home", flush=True)
            return 1
        agent_nick = (args.live_agent_nick or "").strip() or None
        err = check_home_bind(
            args.home,
            args.expected_nick,
            live_agent_nick=agent_nick,
            has_live_listen=bool(args.live_listen),
        )
        if err:
            print(err, flush=True)
            return 3
        return 0
    if args.home:
        err = check_coordinator_nick(args.home)
    elif args.nick and args.pid:
        err = check_nick_seat_pid(args.nick, args.pid)
    else:
        print("INFO pass --home or --nick and --pid", flush=True)
        return 1
    if err:
        print(err, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
