"""FR #6237: scan ear stdout for digest http pull ok (post-restart smoke)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

OK_NEEDLE = "digest http pull ok"


def scan_stdout_log(path: Path | str, *, max_bytes: int = 512_000) -> dict:
    """Return {ok, line, path}. Reads the tail of the ear stdout log."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "line": "", "path": str(p), "error": "missing"}
    data = p.read_bytes()
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    text = data.decode("utf-8", "replace")
    last_ok = ""
    for line in text.splitlines():
        if OK_NEEDLE in line:
            last_ok = line.rstrip()
    return {"ok": bool(last_ok), "line": last_ok, "path": str(p)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FR #6237 smoke: require digest http pull ok in ear stdout")
    ap.add_argument("--log", required=True, help="path to ircBob stdout.log")
    args = ap.parse_args(argv)
    r = scan_stdout_log(args.log)
    if r["ok"]:
        print("OK FR #6237 " + r["line"])
        return 0
    err = r.get("error") or "needle missing"
    print("FAIL FR #6237 digest http pull ok not found in " + r["path"] + " (" + err + ")", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
