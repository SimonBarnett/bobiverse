"""FR #7585: an ear that omits model must clear a sticky Cursor Models label."""
from __future__ import annotations

import bobreport


def test_fr7585_strip_lists_model_when_omitted():
    out = bobreport.strip_legacy_cursor_bridge_from_fuel_payload({"pcent": {}})
    assert "model" in out["cleared"]
    assert "model" not in out or out.get("model") is None


def test_fr7585_real_model_is_kept():
    out = bobreport.strip_legacy_cursor_bridge_from_fuel_payload({"model": "grok-build"})
    assert out.get("model") == "grok-build"
    assert "model" not in out.get("cleared", [])


def test_fr7585_merge_drops_stored_legacy_model_when_payload_omits_it():
    doc = {"v": 1, "machines": {"box-a": {"id": "box-a", "model": "Cursor Models"}}}
    payload = bobreport.strip_legacy_cursor_bridge_from_fuel_payload({"nick": "box-a-1"})
    assert "model" not in payload
    bobreport._apply_merge_payload(doc, "box-a", payload)
    stored = doc["machines"]["box-a"].get("model")
    assert stored in (None, "")
    assert "Cursor Models" not in str(doc["machines"]["box-a"])
