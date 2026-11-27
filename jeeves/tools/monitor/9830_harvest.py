#!/usr/bin/env python3
"""Checklist id ``9830_harvest`` (FR #9880) --- thin alias of lessons_digest_harvest.

Invoke-JeevesMonitorCheck maps ``-Check 9830_harvest`` to this file. Durable
logic lives in ``lessons_digest_harvest.py`` so the next lessons digest number
does not require a rename --- override via env / active held fr-digest detection.
"""
from __future__ import annotations

import sys

import lessons_digest_harvest as core
from _common import run_check


def main(argv: list[str] | None = None) -> int:
    return run_check(
        "9830_harvest",
        "FR #9880 CAST IRON monitor lessons-digest harvest checklist",
        core.check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
