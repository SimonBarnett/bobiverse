"""FR #976: per-machine weekly/pcent replace-latest; unknown clears a stuck 0."""
from __future__ import annotations

from pathlib import Path

import bobreport
import registered_machines


def _home(tmp_path: Path) -> Path:
    registered_machines.save_registered(tmp_path, {"win-mpre8vi4u6u", "marchhare"})
    return tmp_path


def test_weekly_zero_then_unknown_clears(tmp_path: Path):
    home = _home(tmp_path)
    mid = "win-mpre8vi4u6u"
    # First report: measured weekly=0 (exhausted).
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 0,
            "weekly_known": True,
            "period_end": "2026-10-10T14:48:00Z",
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("weekly") == 0

    # Later: xAI weekly unknown — must clear, not leave 0 forever.
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": None,
            "weekly_known": False,
            "period_end": "2026-10-10T14:48:00Z",
        },
    )
    ent2 = bobreport.load_digest(home)["machines"][mid]
    assert "weekly" not in ent2 or ent2.get("weekly") is None


def test_weekly_replace_latest_not_ratchet(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "weekly": 8, "weekly_known": True}
    )
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "weekly": 42, "weekly_known": True}
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("weekly") == 42  # replace-latest, not min(8,42)


def test_pcent_replace_latest_not_ratchet(tmp_path: Path):
    home = _home(tmp_path)
    mid = "flamingo"
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "pcent": {"grok-chat": 5, "cursor-models": 10},
        },
    )
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "pcent": {"grok-chat": 95, "cursor-models": 10},
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent["pcent"]["grok-chat"] == 95


def test_pool_account_stamps_real_nick_not_legacy_alias(tmp_path: Path):
    home = _home(tmp_path)
    mid = "win-mpre8vi4u6u"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "cursor_pools": [
                {
                    "group_id": "grok-chat",
                    "remaining_pct": 96,
                    "account": "bob-ionos",  # legacy alias from reporter
                }
            ],
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    rows = ent.get("cursor_pools") or []
    assert rows
    # Prefer real nick bob-<canonical mid>, not legacy bob-ionos.
    assert rows[0].get("account") == f"bob-{mid}"
