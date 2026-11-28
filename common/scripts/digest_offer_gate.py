"""FR #10055 / #10057 / #10059: offer gates for finished FIX rows and the operator wave."""
from __future__ import annotations


def finished_fix_reoffer_reason(row: dict) -> str | None:
    """Do not offer a FIX the seat already finished (FR #10055)."""
    task = str(row.get("task") or "").strip().upper()
    if task != "FIX":
        return None
    done = row.get("recent_done_keys") or []
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    key = "%s#%s" % (repo, num) if repo and num else ""
    if key and key in {str(k) for k in done}:
        return "finished-fix"
    return None


def outside_operator_wave_reason(row: dict) -> str | None:
    """While an operator wave is open, do not offer rows outside it (FR #10057)."""
    wave = row.get("operator_wave_open")
    if not wave:
        return None
    num = str(row.get("id") or "").strip().lstrip("#")
    allowed = {str(n).lstrip("#") for n in wave}
    if num and num not in allowed:
        return "outside-operator-wave"
    return None


def open_depend_blocks(depend_state: str, labels: list) -> bool:
    """An OPEN Depends-on blocks the offer. A held digest always blocks (FR #10059)."""
    if str(depend_state or "").strip().lower() != "open":
        return False
    labs = {str(x).strip().lower() for x in (labels or [])}
    if "hold" in labs or "on-hold" in labs:
        return True
    return True
