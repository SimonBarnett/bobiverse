"""bob-* shop-channel ops: KICK invalid workers, MODE +o, NAMES (raw outbox verbs).

Spec: agentic_build FR two-persistent-workers LOCKED 27 / A23 "bob-{machine} is ops in
their own shop channel" and LOCKED 15 / A10 "Bob monitors worker processes and restarts
deaf ones". A bob-* ear may therefore remove nicks from #{machine} that have no live
process behind them (leaked test nicks, dead seats). This module is pure logic plus a
small CLI; irc_agent sends the lines raw only for a bob-* nick on its OWN shop channel.

Ergo channel op: with ChanServ disabled, only the creator of an empty channel gets
op. FR #313: bob-* REGISTER #{machine} via ChanServ after JOIN (see shop_chanserv)
so founder/op persists. KICK/MODE without op returns numeric 482; the agent logs
it (INFO shop-op 482 ...) so the gap is visible.

CLI (queues lines in <home>/outbox.txt; the running irc_agent drains them):
  python scripts/shop_ops.py invalid --home ~/.agentic-irc-bobiverse --nick bob-marchhare
  python scripts/shop_ops.py kick-invalid --home ... --nick bob-marchhare [--dry-run]
  python scripts/shop_ops.py names --home ... --nick bob-marchhare
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bobreport  # noqa: E402
import talk_seat_pid  # noqa: E402

KICK_RE = re.compile(r"^KICK (?P<chan>#\S+) (?P<nick>[^\s:]+)(?: :(?P<reason>.*))?$")
MODE_RE = re.compile(r"^MODE (?P<chan>#\S+) (?P<mode>[+-][ov]) (?P<nick>[^\s:]+)$")
NAMES_RE = re.compile(r"^NAMES (?P<chan>#\S+)$")
MAX_REASON = 120
DEFAULT_REASON = "invalid worker: no live process behind nick (bob shop ops)"


def own_shop(own_nick: str) -> str | None:
    """#{machine} for a bob-{machine} nick, else None (seats / w-* / humans get nothing)."""
    n = (own_nick or "").strip().lower().rstrip("_")
    if n.endswith("_l"):
        n = n[:-2]
    if not n.startswith("bob-"):
        return None
    mid = bobreport.machine_from_nick(n)
    if not mid:
        return None
    try:
        return bobreport.shop_channel(mid)
    except ValueError:
        return None


def raw_op_line(line: str, own_nick: str) -> str | None:
    """Return the raw IRC line to send, or None if this outbox line is not an allowed op.

    Allowed only for bob-* nicks and only on their own #{machine}: KICK, MODE +/-o|v, NAMES.
    Never #bobiverse (Jeeves' channel) and never kicking ourselves / Jeeves.
    """
    shop = own_shop(own_nick)
    if not shop:
        return None
    # Collapse CR/LF so outbox multi-line paste cannot smuggle a second verb.
    t = (line or "").replace("\r", " ").replace("\n", " ").strip()
    m = KICK_RE.match(t)
    if m:
        if m.group("chan").lower() != shop:
            return None
        victim = m.group("nick")
        low = victim.lower()
        if low in {(own_nick or "").strip().lower(), "jeeves"} or low.startswith("bob-"):
            return None
        reason = (m.group("reason") or DEFAULT_REASON).replace("\r", " ").replace("\n", " ")
        return f"KICK {shop} {victim} :{reason[:MAX_REASON]}"
    m = MODE_RE.match(t)
    if m:
        if m.group("chan").lower() != shop:
            return None
        return f"MODE {shop} {m.group('mode')} {m.group('nick')}"
    m = NAMES_RE.match(t)
    if m:
        if m.group("chan").lower() != shop:
            return None
        return f"NAMES {shop}"
    return None


def nick_pid(nick: str) -> tuple[str, int] | None:
    """(machine, pid) for w-<short>-<pid> workers and <machine>-<pid> talk seats."""
    n = (nick or "").strip().rstrip("_")
    w = bobreport.parse_worker_nick(n)
    if w:
        mid, pid = w
        return mid, int(pid)
    s = talk_seat_pid.parse_talk_seat_nick(n)
    if s:
        mid, pid = s
        return mid, int(pid)
    return None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def invalid_shop_workers(
    members: Iterable[str],
    machine_id: str,
    alive: Callable[[int], bool] = pid_alive,
) -> list[str]:
    """Worker/seat nicks of THIS machine whose pid is not running. Humans, bob-*, Jeeves never."""
    mid = bobreport.normalize_machine_id(machine_id)
    out: list[str] = []
    for raw in members:
        nick = raw.lstrip("@+%&~")
        parsed = nick_pid(nick)
        if not parsed:
            continue
        nmid, pid = parsed
        if nmid != mid:
            continue  # remote box: we cannot see its processes
        if not alive(pid):
            out.append(nick)
    return sorted(set(out))


def members_from_log(lines: list[str], channel: str) -> set[str]:
    """Replay the last 353 for channel plus JOIN/PART/QUIT/KICK/NICK after it."""
    chan = channel.lower()
    start = -1
    for i, line in enumerate(lines):
        parts = line.split(" ")
        if len(parts) > 4 and parts[1] == "353" and parts[4].lower() == chan:
            start = i
    mem: set[str] = set()
    idx = 0
    if start >= 0:
        # consecutive 353s form one reply
        j = start
        while j >= 0:
            p = lines[j].split(" ")
            if len(p) > 4 and p[1] == "353" and p[4].lower() == chan:
                mem.update(n.lstrip("@+%&~") for n in lines[j].split(" :", 1)[1].split())
                j -= 1
            else:
                break
        idx = start + 1
    rx = re.compile(r"^:([^!\s]+)!\S+ (JOIN|PART|QUIT|KICK|NICK)\s*(.*)$")
    for line in lines[idx:]:
        m = rx.match(line)
        if not m:
            continue
        nick, cmd, rest = m.groups()
        rest_l = rest.lstrip(":").lower()
        if cmd == "JOIN" and rest_l.split(" ")[0] == chan:
            mem.add(nick)
        elif cmd == "PART" and rest_l.split(" ")[0] == chan:
            mem.discard(nick)
        elif cmd == "QUIT":
            mem.discard(nick)
        elif cmd == "KICK":
            bits = rest.split(" ")
            if len(bits) > 1 and bits[0].lower() == chan:
                mem.discard(bits[1])
        elif cmd == "NICK" and nick in mem:
            mem.discard(nick)
            mem.add(rest.lstrip(":").strip())
    return mem


def kick_lines(channel: str, nicks: Iterable[str], reason: str = DEFAULT_REASON) -> list[str]:
    return [f"KICK {channel} {n} :{reason[:MAX_REASON]}" for n in nicks]


def _append_outbox(home: Path, lines: list[str]) -> None:
    with (home / "outbox.txt").open("a", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cmd", choices=["invalid", "kick-invalid", "names"])
    p.add_argument("--home", required=True)
    p.add_argument("--nick", required=True, help="our bob-{machine} nick")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reason", default=DEFAULT_REASON)
    a = p.parse_args(argv)
    home = Path(a.home).expanduser()
    shop = own_shop(a.nick)
    if not shop:
        print("ERROR shop ops are bob-* only", file=sys.stderr)
        return 2
    if a.cmd == "names":
        if not a.dry_run:
            _append_outbox(home, [f"NAMES {shop}"])
        print(f"NAMES {shop}")
        return 0
    log = home / "irc.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.is_file() else []
    mem = members_from_log(lines, shop)
    bad = invalid_shop_workers(mem, shop[1:])
    print(f"members {shop}: {' '.join(sorted(mem))}")
    print(f"invalid: {' '.join(bad) if bad else '-'}")
    if a.cmd == "kick-invalid" and bad:
        out = kick_lines(shop, bad, a.reason)
        if not a.dry_run:
            _append_outbox(home, out)
        for line in out:
            print(("DRY " if a.dry_run else "QUEUED ") + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
