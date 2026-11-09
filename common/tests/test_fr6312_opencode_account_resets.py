"""FR #6312: digest keeps opencode_account; third-layout resetsAt parse (ms/s/ISO)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bobcallback  # noqa: E402
import bobreport  # noqa: E402
import opencode_fuel as of  # noqa: E402

MID = "marchhare"
NOW_MS = 1_700_000_000_000


def _roster(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": [MID]}),
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_fr6312_parse_resets_at_ms_s_iso_missing_past():
    future_ms = NOW_MS + 3 * 3600 * 1000
    assert of.parse_resets_at_to_epoch_ms(future_ms) == future_ms
    # Epoch seconds (below 1e12 heuristic).
    future_s = future_ms // 1000
    assert of.parse_resets_at_to_epoch_ms(future_s) == future_ms
    assert of.parse_resets_at_to_epoch_ms(str(future_s)) == future_ms
    iso = "2023-11-14T22:13:20Z"  # NOW_MS as ISO UTC
    assert of.parse_resets_at_to_epoch_ms(iso) == NOW_MS
    assert of.parse_resets_at_to_epoch_ms(None) is None
    assert of.parse_resets_at_to_epoch_ms("") is None
    assert of.parse_resets_at_to_epoch_ms("not-a-reset") is None
    # Past absolute time still parses (label may be null; never invent).
    past_ms = NOW_MS - 3600 * 1000
    assert of.parse_resets_at_to_epoch_ms(past_ms) == past_ms


def test_fr6312_third_layout_resets_at_variants():
    """Schema C (go.rolling/weekly/monthly.percent) must paint resets_at / error."""
    future_ms = NOW_MS + 2 * 3600 * 1000
    future_s = future_ms // 1000
    iso_future = of._epoch_ms_to_iso_z(future_ms)
    assert iso_future

    cases = [
        ("ms", future_ms, True),
        ("s", future_s, True),
        ("iso", iso_future, True),
        ("missing", None, False),
        ("past", NOW_MS - 60_000, "past"),
        ("bad", "not-a-reset", False),
    ]
    for name, resets_at, expect in cases:
        meter = {"percent": 12, "limited": False}
        if resets_at is not None:
            meter["resetsAt"] = resets_at
        doc = {"go": {"rolling": meter, "weekly": dict(meter), "monthly": dict(meter)}}
        read = of.interpret_go_zen_usage_response(
            200, json.dumps(doc), now_ms=NOW_MS
        )
        assert read["kind"] == "json", name
        assert read.get("schema") == "go-limits", name
        rolling = read["windows"]["rolling"]
        assert rolling["used_pct"] == 12, name
        assert rolling.get("source") == of.GO_ZEN_USAGE_SOURCE, name
        if expect is True:
            assert rolling.get("reset_label"), name
            assert rolling.get("resets_at"), name
            assert rolling.get("error") in (None, ""), name
        elif expect == "past":
            assert rolling.get("reset_label") in (None, ""), name
            assert rolling.get("resets_at"), name
            assert rolling.get("error") in (None, ""), name
        else:
            assert rolling.get("reset_label") in (None, ""), name
            assert rolling.get("resets_at") in (None, ""), name
            assert rolling.get("error") == "reset unavailable", name


def test_fr6312_hub_merge_roundtrip_opencode_account_and_window_reset(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    wins = {
        "rolling": {
            "status": "known",
            "used_pct": 10,
            "remaining_pct": 90,
            "reset_label": "2h 0m",
            "resets_at": "2023-11-14T22:13:20Z",
            "fetched_at": "2023-11-14T20:13:20Z",
            "source": of.GO_ZEN_USAGE_SOURCE,
            "limited": False,
        },
        "week": {
            "status": "known",
            "used_pct": 50,
            "remaining_pct": 50,
            "reset_label": None,
            "fetched_at": "2023-11-14T20:13:20Z",
            "source": of.GO_ZEN_USAGE_SOURCE,
            "error": "reset unavailable",
            "limited": False,
        },
        "month": {
            "status": "known",
            "used_pct": 20,
            "remaining_pct": 80,
            "reset_label": None,
            "fetched_at": "2023-11-14T20:13:20Z",
            "source": of.GO_ZEN_USAGE_SOURCE,
            "error": "reset unavailable",
            "limited": False,
        },
    }
    payload = {
        "op": "merge",
        "machine": MID,
        "id": MID,
        "online": True,
        "opencode_account": "default",
        "opencode_windows": wins,
        "pcent": {"opencode-go": 10},
    }
    # Reject key-shaped labels (never hold key material).
    bad = dict(payload)
    bad["opencode_account"] = "password=FAKE_SHOULD_DROP"
    wire_bad = json.dumps(bad, separators=(",", ":")).encode("utf-8")
    code_bad, _ = bobcallback.handle_report_post(
        {"Content-Type": "application/json"},
        wire_bad,
        tmp_path,
        briefer_nick="Jeeves",
    )
    assert code_bad in (200, 204, 400), code_bad

    wire = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    code, _ = bobcallback.handle_report_post(
        {"Content-Type": "application/json"},
        wire,
        tmp_path,
        briefer_nick="Jeeves",
    )
    assert code in (200, 204), code

    digest = bobreport.build_digest_object(tmp_path, "Jeeves")
    exported = (digest.get("machines") or {}).get(MID) or {}
    assert exported.get("opencode_account") == "default"
    assert "password=" not in json.dumps(exported)
    out_wins = exported.get("opencode_windows") or {}
    assert out_wins["rolling"].get("resets_at")
    assert out_wins["rolling"].get("reset_label") == "2h 0m"
    assert out_wins["week"].get("error") == "reset unavailable"
    assert out_wins["week"].get("resets_at") in (None, "")

    # Null clear via cleared[] (same semantics as grok_account).
    clear_payload = {
        "op": "merge",
        "machine": MID,
        "id": MID,
        "opencode_account": None,
        "cleared": ["opencode_account"],
    }
    wire_clear = json.dumps(clear_payload, separators=(",", ":")).encode("utf-8")
    code_c, _ = bobcallback.handle_report_post(
        {"Content-Type": "application/json"},
        wire_clear,
        tmp_path,
        briefer_nick="Jeeves",
    )
    assert code_c in (200, 204), code_c
    after = (bobreport.build_digest_object(tmp_path, "Jeeves").get("machines") or {}).get(
        MID
    ) or {}
    assert after.get("opencode_account") in (None, "")
    # Windows must not be dropped by the account clear.
    assert isinstance(after.get("opencode_windows"), dict)


def test_fr6312_webhooks_doc_names_opencode_account():
    root = Path(__file__).resolve().parents[2]
    text = (root / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "opencode_account" in text
    assert "grok_account" in text
