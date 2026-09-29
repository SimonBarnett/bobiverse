#!/usr/bin/env python3
"""Moot CLI + in-process state machine. Floor discipline. No sockets."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seal
import wire

MOOT_ROSTER_MAX = 16


def _home(h: str | None) -> Path:
    if h:
        os.environ["AGENTIC_IRC_HOME"] = str(Path(h).expanduser())
    return seal.home()


def _paths(home: Path, mid: str) -> tuple[Path, Path]:
    d = home / "moot"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{mid}.json", d / f"{mid}.txt"


def load_state(home: Path, mid: str) -> dict:
    jp, _ = _paths(home, mid)
    if not jp.exists():
        return {}
    return json.loads(jp.read_text(encoding="utf-8"))


def save_state(home: Path, st: dict) -> None:
    jp, _ = _paths(home, st["id"])
    payload = json.dumps(st, indent=2) + "\n"
    tmp = jp.with_name(jp.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(jp)


def append_tx(home: Path, mid: str, nick: str, verb: str, text: str) -> None:
    _, tp = _paths(home, mid)
    extra = f" {text}" if text else ""
    with tp.open("a", encoding="utf-8") as f:
        f.write(f"{int(time.time())} {nick} {verb}{extra}\n")


def outbox_line(home: Path, line: str) -> None:
    p = home / "outbox.txt"
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def apply_moot(st: dict | None, src: str, line: wire.MootLine, home: Path | None = None) -> dict:
    """Update state from an observed MOOT line. First OPEN wins. Persist when home is set."""
    out = _apply_moot(st, src, line, home)
    if home is not None and out.get("id"):
        save_state(home, out)
    return out


def _apply_moot(st: dict | None, src: str, line: wire.MootLine, home: Path | None = None) -> dict:
    """In-memory apply. OPEN/JOIN/FLOOR/SAY/YIELD/CLOSE go to transcript when home is set."""
    st = dict(st or {})
    if line.verb == "OPEN":
        if st.get("id") and st.get("state") != "closed":
            return st  # first wins
        if st.get("id") == line.moot_id and st.get("chair") and st.get("chair") != src:
            return st
        chair = line.fields[0] if line.fields else src
        mode = line.fields[1] if len(line.fields) > 1 else "floor"
        st = {
            "v": 1,
            "id": line.moot_id,
            "mode": mode,
            "state": "open",
            "chair": chair,
            "floor": None,
            "roster": [chair] if chair else [],
            "seq_by_nick": {},
            "topic": line.text,
        }
        if home:
            append_tx(home, st["id"], src, "OPEN", line.text)
        return st
    if not st or st.get("id") != line.moot_id or st.get("state") == "closed":
        if line.verb == "CLOSE" and st.get("id") == line.moot_id:
            st["state"] = "closed"
            st["floor"] = None
        return st
    roster = list(st.get("roster") or [])
    src_l = src.lower()

    if line.verb == "JOIN":
        if src not in roster and src_l not in [x.lower() for x in roster]:
            if len(roster) < MOOT_ROSTER_MAX:
                roster.append(src)
        st["roster"] = roster
        if home:
            append_tx(home, st["id"], src, "JOIN", line.text)
    elif line.verb == "PART":
        st["roster"] = [x for x in roster if x.lower() != src_l]
        if st.get("floor") and st["floor"].lower() == src_l:
            st["floor"] = None
    elif line.verb == "HANDOFF":
        if src.lower() != str(st.get("chair", "")).lower():
            return st
        newc = line.fields[0] if line.fields else ""
        if newc.lower() not in [x.lower() for x in roster]:
            return st
        st["chair"] = newc
    elif line.verb == "FLOOR":
        if src.lower() != str(st.get("chair", "")).lower():
            return st
        nick = line.fields[0] if line.fields else ""
        st["floor"] = nick
        if home:
            append_tx(home, st["id"], src, "FLOOR", nick)
    elif line.verb == "YIELD":
        if not st.get("floor") or src.lower() != str(st["floor"]).lower():
            return st
        to = line.fields[0] if line.fields else "*"
        if to == "*":
            st["floor"] = None
        elif to.lower() in [x.lower() for x in roster]:
            st["floor"] = to
        else:
            st["floor"] = None
        if home:
            append_tx(home, st["id"], src, "YIELD", to)
    elif line.verb == "SAY":
        if st.get("mode") == "floor":
            fl = st.get("floor")
            if not fl or src.lower() != fl.lower():
                return st
        seq = int(line.fields[0]) if line.fields else 0
        prev = int((st.get("seq_by_nick") or {}).get(src, 0))
        if seq <= prev:
            return st
        st.setdefault("seq_by_nick", {})[src] = seq
        if home:
            append_tx(home, st["id"], src, "SAY", line.text)
    elif line.verb == "ROSTER":
        if src.lower() == str(st.get("chair", "")).lower() and line.text:
            st["roster"] = [x for x in line.text.split(",") if x]
    elif line.verb == "CLOSE":
        if src.lower() != str(st.get("chair", "")).lower():
            return st
        st["state"] = "closed"
        st["floor"] = None
        if home:
            append_tx(home, st["id"], src, "CLOSE", line.text)
    elif line.verb == "POINT":
        if home:
            append_tx(home, st["id"], src, "POINT", line.text)
    return st


def _id(args) -> str:
    return args.id or secrets.token_hex(8)


def main() -> None:
    p = argparse.ArgumentParser(description="moot CLI")
    p.add_argument("--home", default="")
    sub = p.add_subparsers(dest="cmd", required=True)
    def add(name):
        s = sub.add_parser(name)
        s.add_argument("--id", default="")
        s.add_argument("--nick", default="")
        s.add_argument("--channel", default="#ops")
        return s
    o = add("open")
    o.add_argument("--topic", default="")
    o.add_argument("--mode", default="floor", choices=["floor", "free"])
    add("join")
    s = add("say")
    s.add_argument("--text", default="")
    add("point").add_argument("--why", default="", dest="text")
    y = add("yield")
    y.add_argument("--to", default="*")
    f = add("floor")
    f.add_argument("--to", default="")
    add("roll")
    add("close").add_argument("--summary", default="", dest="text")
    add("status")
    args = p.parse_args()
    home = _home(args.home or None)
    nick = args.nick or "me"
    mid = args.id or secrets.token_hex(8)
    st = load_state(home, mid) if args.cmd != "open" else {}
    line = None
    if args.cmd == "open":
        line = f"MOOT v1 OPEN {mid} {nick} {args.mode} :{args.topic}"
        parsed = wire.parse_moot_line(line)
        st = apply_moot({}, nick, parsed, home)
        save_state(home, st)
    elif args.cmd == "join":
        line = f"MOOT v1 JOIN {mid}"
    elif args.cmd == "say":
        seq = int((st.get("seq_by_nick") or {}).get(nick, 0)) + 1
        line = f"MOOT v1 SAY {mid} {seq} :{args.text}"
    elif args.cmd == "point":
        line = f"MOOT v1 POINT {mid} :{getattr(args, 'text', '')}"
    elif args.cmd == "yield":
        line = f"MOOT v1 YIELD {mid} {args.to}"
    elif args.cmd == "floor":
        line = f"MOOT v1 FLOOR {mid} {args.to}"
    elif args.cmd == "roll":
        line = f"MOOT v1 ROLL {mid}"
    elif args.cmd == "close":
        line = f"MOOT v1 CLOSE {mid} :{getattr(args, 'text', '')}"
    elif args.cmd == "status":
        print(json.dumps(st or load_state(home, mid), indent=2))
        return
    if line:
        outbox_line(home, line)
        parsed = wire.parse_moot_line(line)
        if parsed:
            if args.cmd != "open":
                st = load_state(home, parsed.moot_id) or st
            st = apply_moot(st, nick, parsed, home)
            if st:
                save_state(home, st)


if __name__ == "__main__":
    main()
