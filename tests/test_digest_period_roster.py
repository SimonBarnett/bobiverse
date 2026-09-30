"""Period-roll lesser reset + ChanServ roster gate."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import registered_machines


def test_merge_pcent_lesser_same_period_keeps_min():
    out = bobreport._merge_pcent_lesser({"cursor-models": 40}, {"cursor-models": 90}, replace=False)
    assert out["cursor-models"] == 40


def test_merge_pcent_lesser_replace_allows_100():
    out = bobreport._merge_pcent_lesser({"cursor-models": 5}, {"cursor-models": 100}, replace=True)
    assert out["cursor-models"] == 100


def test_period_rolled_detects_new_window():
    assert bobreport._period_rolled("2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z") is True
    assert bobreport._period_rolled("2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z") is False
    assert bobreport._period_rolled(None, "2026-10-01T00:00:00Z") is True


def test_apply_merge_period_roll_allows_pcent_rise(tmp_path: Path):
    registered_machines.save_registered(tmp_path, {"flamingo", "ionos"})
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"]["pcent"] = {"cursor-models": 12}
    doc["machines"]["flamingo"]["cursor_period_end"] = "2026-09-01T00:00:00Z"
    bobreport.save_digest(tmp_path, doc)
    out = bobreport.apply_callback(
        tmp_path,
        {
            "op": "merge",
            "id": "flamingo",
            "pcent": {"cursor-models": 100},
            "cursor_period_end": "2026-10-01T00:00:00Z",
        },
    )
    assert out.ok
    loaded = bobreport.load_digest(tmp_path)
    assert loaded["machines"]["flamingo"]["pcent"]["cursor-models"] == 100
    assert loaded["machines"]["flamingo"]["cursor_period_end"] == "2026-10-01T00:00:00Z"


def test_apply_merge_rejects_unregistered_machine(tmp_path: Path):
    registered_machines.save_registered(tmp_path, {"flamingo"})
    out = bobreport.apply_callback(
        tmp_path,
        {"op": "merge", "id": "marchhare", "pcent": {"cursor-models": 50}},
    )
    assert not out.ok
    assert out.err == "not registered"


def test_ensure_seats_prunes_unregistered(tmp_path: Path):
    registered_machines.save_registered(tmp_path, {"flamingo"})
    doc = {
        "v": 1,
        "machines": {
            "flamingo": bobreport._empty_machine("flamingo"),
            "ghost-box": bobreport._empty_machine("ghost-box"),
        },
        "events": [],
    }
    out = bobreport._ensure_seats(doc, tmp_path)
    assert "flamingo" in out["machines"]
    assert "ghost-box" not in out["machines"]


def test_build_digest_object_exports_chanserv_roster_and_chair_channels(tmp_path: Path):
    registered_machines.save_registered(
        tmp_path, {"flamingo", "ionos", "win-mpre8vi4u6u"}
    )
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"]["online"] = True
    doc["machines"]["flamingo"]["pcent"] = {"cursor-models": 12, "grok-chat": 40}
    doc["machines"]["flamingo"]["cursor_period_end"] = "2026-10-16T17:23:01Z"
    doc["machines"]["flamingo"]["period_end"] = "2026-10-04T00:36:16Z"
    bobreport.save_digest(tmp_path, doc)

    out = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert set(out["machines"].keys()) == {"flamingo", "ionos", "win-mpre8vi4u6u"}
    assert "marchhare" not in out["machines"]
    assert out["chair_channels"] == [
        "#bobiverse",
        "#flamingo",
        "#ionos",
        "#win-mpre8vi4u6u",
    ]
    by_id = {p["id"]: p for p in out["cursor_pools"]}
    assert by_id["cursor-models"]["period_end"] == "2026-10-16T17:23:01Z"
    assert by_id["grok-weekly"]["period_end"] == "2026-10-04T00:36:16Z"


def test_cursor_pool_period_splits_billing_and_sand():
    ent = {
        "cursor_period_end": "2026-10-16T17:23:01Z",
        "period_end": "2026-10-04T00:36:16Z",
    }
    pe, _ = bobreport._cursor_pool_period(ent, "cursor-models")
    assert pe == "2026-10-16T17:23:01Z"
    pe_g, _ = bobreport._cursor_pool_period(ent, "grok-weekly")
    assert pe_g == "2026-10-04T00:36:16Z"
    pe_chat, _ = bobreport._cursor_pool_period(ent, "grok-chat")
    assert pe_chat == "2026-10-04T00:36:16Z"
