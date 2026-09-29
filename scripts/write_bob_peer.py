#!/usr/bin/env python3
"""Write bob-peers/<id>.json from Watch-shaped JSON or a BOB v1 POINT line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bobstat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", default=None, help="AGENTIC_IRC_HOME (fleet bob-peers parent)")
    ap.add_argument("--point", default=None, help="BOB v1 POINT trailing text")
    ap.add_argument("--refresh-cursor", action="store_true", help="merge Cursor Models remaining when weekly=0")
    ap.add_argument("--stdin-json", action="store_true", help="read peer JSON object from stdin")
    args = ap.parse_args(argv)

    home = Path(args.home or Path.home() / ".agentic-irc-bobiverse").expanduser()
    doc: dict | None = None
    if args.point:
        doc = bobstat.parse_bob_point(args.point)
    elif args.stdin_json:
        raw = sys.stdin.read()
        if raw.strip():
            doc = json.loads(raw)
    if not doc:
        return 1
    bobstat.write_peer(home, doc)
    mid = str(doc.get("id") or "")
    if args.refresh_cursor and mid:
        bobstat.refresh_peer_cursor_remaining(home, mid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
