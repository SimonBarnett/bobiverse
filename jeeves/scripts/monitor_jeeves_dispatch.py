"""Token-quiet ircJeeves dispatch watch.

Prints one final line, or one STOP line. Does not print the hand-out order
or the chair log. Stops the ircJeeves service on the chair host when a new
log line offers or accepts a held FR or a dependant of one.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(r"\\walrus\c$\Users\Administrator\.bobiverse")
LOG = Path(r"\\walrus\c$\ai\jeeves\logs\stdout.log")
HELD = {"hold", "on-hold"}
DEP = re.compile(r"(?im)depends-on:\**\s*:?\s*(?:SimonBarnett/[\w.-]+)?#(\d+)")
OFFER = re.compile(r"(?i)(?:offered|ACK status=ok).{0,120}#(\d+)")


def _num(row: dict) -> int | None:
    m = re.search(r"(\d+)", str(row.get("id") or ""))
    return int(m.group(1)) if m else None


def _labs(row: dict) -> set[str]:
    out = set()
    for x in row.get("labels") or []:
        out.add(str(x.get("name") if isinstance(x, dict) else x).lower())
    return out


def blocked_ids() -> set[int]:
    q = json.loads((HOME / "queue.json").read_text(encoding="utf-8"))
    rows = [
        r
        for r in (q.get("unaccepted") or []) + (q.get("accepted") or [])
        if str(r.get("repo") or "").lower() == "simonbarnett/bobiverse"
    ]
    by = {n: r for r in rows if (n := _num(r))}
    held = {n for n, r in by.items() if HELD.intersection(_labs(r))}
    deps = {n: {int(x) for x in DEP.findall(r.get("body") or "")} for n, r in by.items()}
    blocked = set(held)
    changed = True
    while changed:
        changed = False
        for n, ds in deps.items():
            if n not in blocked and ds & blocked:
                blocked.add(n)
                changed = True
    return blocked


def _stop(n: int) -> None:
    subprocess.call(["sc.exe", r"\\walrus", "stop", "ircJeeves"])
    print(f"STOP #{n}", flush=True)


def main() -> int:
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    try:
        pos = LOG.stat().st_size
    except OSError:
        print("ERROR log", flush=True)
        return 2
    end = time.time() + seconds
    while time.time() < end:
        blocked = blocked_ids()
        try:
            size = LOG.stat().st_size
        except OSError:
            time.sleep(20)
            continue
        if size < pos:
            pos = 0
        if size > pos:
            with LOG.open("rb") as fh:
                fh.seek(pos)
                raw = fh.read()
            pos = size
            text = raw.decode("utf-8", "replace")
            for m in OFFER.finditer(text):
                n = int(m.group(1))
                if n in blocked:
                    _stop(n)
                    return 1
        time.sleep(20)
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
