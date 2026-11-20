#!/usr/bin/env python3
"""Auto-feed check (ported intent from ops/auto-feed.py): chair auto-feed enabled vs stalled."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check


def _idle_offerable_when_off(args) -> str | None:
    """FR #8493: unconfigured or disabled auto-feed must not hide idle+offerable work."""
    try:
        import idle_seats

        doc, code = idle_seats.check(args)
    except Exception:
        return None
    if code != EXIT_FINDING or not isinstance(doc, dict):
        return None
    n_idle = len(doc.get("idle_seats") or [])
    try:
        offerable = int(doc.get("offerable_for_live_seats") or 0)
    except (TypeError, ValueError):
        offerable = 0
    if n_idle <= 0 or offerable <= 0:
        return None
    return (
        f"auto-feed off with {n_idle} idle seat(s) and {offerable} offerable row(s); "
        "seats must !bored or enable auto-feed"
    )


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    cfg_paths = [
        chair / "auto-feed.json",
        chair / "config" / "auto-feed.json",
        chair / "autofeed.json",
    ]
    cfg = None
    used = None
    for p in cfg_paths:
        if p.is_file():
            used = p
            try:
                cfg = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception as e:
                findings.append(f"auto-feed config unreadable: {p} ({e})")
                return ({"ok": False, "findings": findings, "path": str(p)}, EXIT_FINDING)
            break
    if cfg is None:
        # Missing config stays OK until idle seats have offerable rows (FR #8493).
        # Do not enable auto-feed from this check; name the gap so it is not silent.
        note = _idle_offerable_when_off(args)
        if note:
            return (
                {
                    "ok": False,
                    "enabled": False,
                    "configured": False,
                    "findings": [note],
                    "note": "no auto-feed config present",
                },
                EXIT_FINDING,
            )
        return (
            {
                "ok": True,
                "enabled": False,
                "configured": False,
                "findings": [],
                "note": "no auto-feed config present",
            },
            EXIT_OK,
        )
    enabled = bool(cfg.get("enabled") or cfg.get("on") or cfg.get("auto_feed"))
    last_error = cfg.get("last_error") or cfg.get("error")
    if enabled and last_error:
        findings.append(f"auto-feed enabled but last_error={last_error!r}")
    elif not enabled:
        note = _idle_offerable_when_off(args)
        if note:
            findings.append(note)
    ok = not findings
    return (
        {
            "ok": ok,
            "enabled": enabled,
            "configured": True,
            "path": str(used),
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "auto_feed",
        "Auto-feed enable/stall check (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
