#!/usr/bin/env python3
"""FR #8427: needs_human false positives from holder_bored / infra-soft GIVEUPs.

FR #8375 made holder_bored (and the other infra/soft seat-churn reasons) never
increment giveup_count nor stamp needs_human. Rows stamped needs_human before
that landed (giveup_reason=holder_bored) starve the offer queue (class of
#8391/#8396/#8413). Detect those false-positive rows and heal them so they
re-offer to a live seat.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    resolve_homes,
    resolve_queue_path,
    run_check,
)


def _ensure_common() -> None:
    from _common import ensure_script_dir_on_path

    # FR #8580 / #8591: no parents[N]; walk upward for gitclaim.py
    ensure_script_dir_on_path("gitclaim.py")



def _load_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def check(args):
    _ensure_common()
    import gitclaim as gc

    chair, digest = resolve_homes(args)
    qpath = resolve_queue_path(chair, digest)
    home = qpath.parent

    healed: list[str] = []
    error: str = ""
    try:
        healed = gc.heal_false_needs_human_for_infra_soft(home)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    findings: list[str] = []
    if healed:
        findings.append(
            "needs_human false positive healed (holder_bored / infra-soft): "
            + ", ".join(healed)
        )
    if error:
        findings.append(f"heal error: {error}")

    remediation = [
        "cleared needs_human + giveup state on rows whose giveup_reason is "
        "holder_bored / infra-soft (FR #8375 set) so they re-offer",
        "see common/scripts/gitclaim.heal_false_needs_human_for_infra_soft (FR #8427)",
    ]
    ok = not findings
    return (
        {
            "ok": ok,
            "findings": findings,
            "healed": healed,
            "healed_count": len(healed),
            "remediation": remediation if findings else [],
            "path_queue": str(qpath),
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "needs_human_false_positive",
        "needs_human false positive from holder_bored / infra-soft GIVEUP (FR #8427)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
