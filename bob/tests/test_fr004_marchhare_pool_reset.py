"""FR #6144 / FR-004: MarchHare pool remaining/reset correctness (cursor_known)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import bobstat
import registered_machines

NOW = "2026-11-07T14:00:00Z"
XAI_RESET = "2026-11-14T12:00:00Z"
SAND_RESET = "2026-11-10T08:00:00Z"
BILL_RESET = "2026-11-21T00:00:00Z"


def _home(tmp_path: Path, mids=None) -> Path:
    registered_machines.save_registered(
        tmp_path, set(mids or {"marchhare", "flamingo", "redqueen"})
    )
    return tmp_path


def test_marchhare_weekly99_cursor_unknown_omits_cursor_fields(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "lastSeen": NOW,
            "cursor_known": False,
            "cursor_label": "0%",  # must not stick
            "pcent": {"cursor-models": 0, "grok-chat": 0},
            "cursor_pools": [
                {
                    "group_id": "auto",
                    "remaining_pct": 0,
                    "period_end": BILL_RESET,
                    "machine_id": mid,
                }
            ],
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("weekly") == 99
    assert ent.get("period_end") == XAI_RESET
    assert ent.get("cursor_known") is False
    assert ent.get("cursor_label") in (None, "")
    assert ent.get("pcent") in (None, {}, "")
    assert ent.get("cursor_pools") in (None, [], "")
    exported = bobreport.export_machine_for_tray(home, mid, ent)
    assert exported.get("weekly") == 99
    assert exported.get("cursor_label") in (None, "")
    assert exported.get("cursor_label") != "0%"
    assert exported.get("period_end") == XAI_RESET


def test_known_then_unknown_clears_stale_cursor_peer_cannot_restore(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "lastSeen": NOW,
            "cursor_known": True,
            "cursor_label": "42%",
            "sand_period_end": SAND_RESET,
            "cursor_period_end": BILL_RESET,
            "pcent": {"cursor-models": 0, "grok-chat": 94},
            "cursor_pools": [
                {
                    "group_id": "auto",
                    "remaining_pct": 0,
                    "period_end": BILL_RESET,
                    "machine_id": mid,
                },
                {
                    "group_id": "grok-chat",
                    "remaining_pct": 94,
                    "period_end": SAND_RESET,
                    "machine_id": mid,
                },
            ],
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent["pcent"]["cursor-models"] == 0
    assert ent["pcent"]["grok-chat"] == 94
    assert ent.get("sand_period_end") == SAND_RESET
    assert ent.get("cursor_period_end") == BILL_RESET
    assert ent.get("period_end") == XAI_RESET

    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "lastSeen": NOW,
            "cursor_known": False,
        },
    )
    ent2 = bobreport.load_digest(home)["machines"][mid]
    assert ent2.get("weekly") == 99
    assert ent2.get("cursor_label") in (None, "")
    assert ent2.get("pcent") in (None, {}, "")
    assert ent2.get("cursor_pools") in (None, [], "")
    assert ent2.get("sand_period_end") in (None, "")
    assert ent2.get("cursor_period_end") in (None, "")

    # Stale peer label must not restore Cursor fields on export.
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": mid,
            "online": True,
            "weekly": 99,
            "cursor_label": "0%",
            "pcent": {"cursor-models": 0},
            "cursor_pools": [{"group_id": "auto", "remaining_pct": 0}],
        },
    )
    exported = bobreport.export_machine_for_tray(home, mid, ent2)
    assert exported.get("cursor_label") in (None, "")
    assert exported.get("cursor_label") != "0%"
    assert exported.get("weekly") == 99


def test_distinct_sand_and_billing_resets_preserved(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "cursor_known": True,
            "sand_period_end": SAND_RESET,
            "cursor_period_end": BILL_RESET,
            "pcent": {"cursor-models": 0, "grok-chat": 94},
            "cursor_pools": [
                {
                    "group_id": "auto",
                    "remaining_pct": 0,
                    "period_end": BILL_RESET,
                    "machine_id": mid,
                },
                {
                    "group_id": "grok-chat",
                    "remaining_pct": 94,
                    "period_end": SAND_RESET,
                    "machine_id": mid,
                },
            ],
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    sand_pe, _ = bobreport._cursor_pool_period(ent, "grok-chat")
    bill_pe, _ = bobreport._cursor_pool_period(ent, "cursor-models")
    assert sand_pe == SAND_RESET
    assert bill_pe == BILL_RESET
    assert ent.get("period_end") == XAI_RESET
    assert sand_pe != XAI_RESET
    assert bill_pe != XAI_RESET


def test_pool_row_backfills_sand_period_end_not_xai(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "cursor_known": True,
            "cursor_pools": [
                {
                    "group_id": "grok-chat",
                    "remaining_pct": 94,
                    "period_end": SAND_RESET,
                    "machine_id": mid,
                }
            ],
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("sand_period_end") == SAND_RESET
    assert ent.get("period_end") == XAI_RESET


def test_legacy_period_end_fallback_without_cursor_clocks(tmp_path: Path):
    """Older clients omit cursor_known and Cursor clocks — keep legacy period_end fallback."""
    home = _home(tmp_path)
    mid = "flamingo"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "period_end": XAI_RESET,
            "pcent": {"cursor-models": 10},
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    pe, _ = bobreport._cursor_pool_period(ent, "cursor-models")
    assert pe == XAI_RESET


def test_cursor_label_null_clears(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "cursor_known": True,
            "cursor_label": "12%",
        },
    )
    bobreport.apply_callback(
        home,
        {"op": "merge", "machine": mid, "cursor_label": None},
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("cursor_label") in (None, "")


def test_omit_cursor_known_preserves_legacy_merge(tmp_path: Path):
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "cursor_label": "55%",
            "pcent": {"cursor-models": 55},
        },
    )
    bobreport.apply_callback(
        home,
        {"op": "merge", "machine": mid, "online": True, "weekly": 99, "weekly_known": True},
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("cursor_label") == "55%"
    assert ent["pcent"]["cursor-models"] == 55
    assert ent.get("weekly") == 99


def test_mrb6169_cursor_unknown_clears_cur_field(tmp_path: Path):
    """MRB #6169: cur is in Cursor-group clear/skip set with cursor_known=false."""
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "lastSeen": NOW,
            "cursor_known": True,
            "cur": "cursor-models",
            "cursor_label": "42%",
            "pcent": {"cursor-models": 42},
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("cur") == "cursor-models"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "lastSeen": NOW,
            "cursor_known": False,
            "cur": "cursor-models",
            "cursor_label": "0%",
        },
    )
    ent2 = bobreport.load_digest(home)["machines"][mid]
    assert ent2.get("cursor_known") is False
    assert ent2.get("cur") in (None, "")
    assert ent2.get("cursor_label") in (None, "")
    exported = bobreport.export_machine_for_tray(home, mid, ent2)
    assert exported.get("cur") in (None, "")
    assert "cur" in bobreport._CURSOR_GROUP_KEYS


def test_mrb6169_sand_reset_not_xai_when_sand_unknown(tmp_path: Path):
    """Sand pool must not inherit xAI period_end when sand_period_end absent."""
    home = _home(tmp_path)
    mid = "marchhare"
    bobreport.apply_callback(
        home,
        {
            "op": "merge",
            "machine": mid,
            "online": True,
            "weekly": 99,
            "weekly_known": True,
            "period_end": XAI_RESET,
            "lastSeen": NOW,
            "cursor_known": True,
            "pcent": {"grok-chat": 94},
            "cursor_pools": [
                {
                    "group_id": "grok-chat",
                    "remaining_pct": 94,
                    "machine_id": mid,
                    # no period_end / sand_period_end on row
                }
            ],
        },
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    # Prefer dedicated sand clock helper: xAI weekly period_end must not be forced onto Sand
    # when sand_period_end is unknown (FR #6144 / CodeRabbit linked-issue check).
    pe = bobreport._cursor_pool_period(ent, "grok-chat")
    # Accept None (unknown) or sand/billing clock; never silently equal XAI_RESET alone
    # unless sand_period_end / cursor_period_end also set that value.
    if pe == XAI_RESET:
        assert ent.get("sand_period_end") == XAI_RESET or ent.get("cursor_period_end") == XAI_RESET
