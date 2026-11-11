"""FR #6248: service owns Go zen usage acquisition; tray does not write handoffs."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import opencode_fuel


PINNED_SCHEMA = {
    "useBalance": True,
    "rollingUsage": {"status": "ok", "usagePercent": 0, "resetInSec": 3600},
    "weeklyUsage": {"status": "ok", "usagePercent": 72, "resetInSec": 23520},
    "monthlyUsage": {"status": "ok", "usagePercent": 36, "resetInSec": 2239200},
}


def test_interpret_pinned_schema_used_to_remaining():
    read = opencode_fuel.interpret_go_zen_usage_response(
        200, json.dumps(PINNED_SCHEMA), now_ms=1_700_000_000_000
    )
    assert read["kind"] == "json"
    assert read["schema"] == "usagePercent"
    week = read["windows"]["week"]
    assert week["used_pct"] == 72
    assert week["remaining_pct"] == 28
    assert week["source"] == opencode_fuel.GO_ZEN_USAGE_SOURCE
    assert week["fetched_at"]
    assert week["reset_label"]
    rolling = read["windows"]["rolling"]
    assert rolling["used_pct"] == 0
    assert rolling["remaining_pct"] == 100


def test_interpret_401_403_malformed_unknown():
    assert opencode_fuel.interpret_go_zen_usage_response(401, "{}")["kind"] == "auth_error"
    assert (
        opencode_fuel.interpret_go_zen_usage_response(403, "{}")["kind"]
        == "entitlement_error"
    )
    bad = opencode_fuel.interpret_go_zen_usage_response(200, '{"nope": true}')
    assert bad["kind"] == "malformed"
    assert bad["windows"]["week"]["status"] == "unknown"
    assert bad["windows"]["week"]["used_pct"] is None


def test_nested_usage_schema():
    body = {
        "usage": {
            "rolling": {"percent": 10, "status": "ok", "resetsAt": 1_700_003_600_000},
            "weekly": {"percent": 50, "status": "ok", "resetsAt": 1_700_010_000_000},
            "monthly": {"percent": 20, "status": "ok", "resetsAt": 1_702_000_000_000},
        }
    }
    read = opencode_fuel.interpret_go_zen_usage_response(
        200, json.dumps(body), now_ms=1_700_000_000_000
    )
    assert read["schema"] == "usage-nested"
    assert read["windows"]["week"]["used_pct"] == 50
    assert read["windows"]["week"]["remaining_pct"] == 50


def test_fuel_doc_and_service_read_via_fixture(monkeypatch):
    fixture = "200\n" + json.dumps(PINNED_SCHEMA)
    monkeypatch.setenv("BOB_OPENCODE_GO_USAGE_FIXTURE", fixture)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_WINDOWS_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    doc = bobreport.read_local_opencode_fuel_doc()
    assert doc["source"] == opencode_fuel.GO_ZEN_USAGE_SOURCE
    assert doc["opencode-go"] == 28  # tightest remaining is weekly 28
    assert doc["windows"]["week"]["remaining_pct"] == 28
    assert doc["windows"]["week"]["used_pct"] == 72
    assert "opencode-free" not in doc.get("pcent", {})
    assert "opencode-free" not in doc


def test_service_enrich_publish_fingerprint_includes_windows(monkeypatch):
    fixture = json.dumps(PINNED_SCHEMA)
    monkeypatch.setenv("BOB_OPENCODE_GO_USAGE_FIXTURE", fixture)
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    doc = bobreport.read_local_opencode_fuel_doc()
    peer = {"id": "marchhare", "ok": True, "pcent": {"grok-chat": 74}}
    oc = bobreport._pcent_from_opencode_fuel_doc(doc)
    wins = bobreport._windows_from_opencode_fuel_doc(doc)
    peer = bobreport.enrich_peer_with_opencode_pcent(peer, oc, wins)
    assert peer["opencode_windows"]["week"]["used_pct"] == 72
    assert peer["opencode_windows"]["week"]["remaining_pct"] == 28
    fp = bobreport.peer_fuel_fingerprint(peer)
    assert "opencode_windows=" in fp
    body = bobreport.build_peer_fuel_merge_payload(peer, "marchhare")
    assert body["opencode_windows"]["week"]["source"] == opencode_fuel.GO_ZEN_USAGE_SOURCE


def test_digest_merge_retains_three_windows():
    doc = {"v": 1, "machines": {}}
    wins = opencode_fuel.interpret_go_zen_usage_response(
        200, json.dumps(PINNED_SCHEMA), now_ms=1_700_000_000_000
    )["windows"]
    bobreport._apply_merge_payload(
        doc,
        "marchhare",
        {
            "op": "merge",
            "machine": "marchhare",
            "opencode_windows": wins,
            "pcent": {"opencode-go": 28},
        },
    )
    ent = doc["machines"]["marchhare"]
    assert ent["opencode_windows"]["rolling"]["used_pct"] == 0
    assert ent["opencode_windows"]["week"]["used_pct"] == 72
    assert ent["opencode_windows"]["month"]["used_pct"] == 36
    assert ent["opencode_windows"]["week"]["remaining_pct"] == 28


def test_tray_save_handoff_is_noop_source_pin():
    src = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / "tray"
        / "src"
        / "Private"
        / "Get-BobIrc.ps1"
    ).read_text(encoding="utf-8")
    fn = src[
        src.find("function Save-BobXaiWeeklyHandoff") : src.find(
            "function Write-BobIrcStatus"
        )
    ]
    assert "FR #6248" in fn
    assert "return" in fn
    assert fn.find("return") < fn.find("WriteAllText")
    assert "no tray usage handoff write" in src


def test_xai_acquisition_skips_tray_handoff(tmp_path, monkeypatch):
    """Tray handoff under BOB_INSTALL_ROOT must never be an acquisition source (FR #6248).

    FR #6699: under LocalSystem !build, FR #6270 may prefer interactive-profile.
    Force system-profile skip so this pin stays about handoff, not interactive logs.
    """
    handoff = tmp_path / "run" / "xai-weekly.json"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        json.dumps(
            {
                "provider": "xai",
                "window": "weekly",
                "direction": "remaining",
                "remaining_pct": 43,
                "weekly_known": True,
                "fetched_at": "2026-11-08T15:00:00Z",
                "source": "collector-handoff",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    (tmp_path / "systemprofile").mkdir()
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.delenv("BOB_GROK_WEEKLY_USER_HOME", raising=False)
    # Keep FR #6270 interactive auto-pick off for this handoff-skip pin.
    monkeypatch.setenv("BOB_WEEKLY_FORCE_SYSTEM_PROFILE", "1")
    reading = bobreport.read_local_xai_weekly()
    assert reading is None
    assert bobreport._last_xai_acquisition.get("identity") == "system-profile-skipped"
    # Handoff file still exists; acquisition must not have used it.
    assert handoff.is_file()
    assert bobreport.xai_weekly_handoff_path() == handoff


def test_fetch_go_zen_usage_sends_bearer(monkeypatch):
    captured = {}

    class Resp:
        status = 200

        def read(self):
            return json.dumps(PINNED_SCHEMA).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout=5.0):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            return Resp()

    monkeypatch.setattr(
        opencode_fuel.urllib.request,
        "build_opener",
        lambda *a, **k: Opener(),
    )
    read = opencode_fuel.fetch_go_zen_usage("FAKE_TEST_KEY_NOT_REAL")
    assert captured["auth"] == "Bearer FAKE_TEST_KEY_NOT_REAL"
    assert captured["url"].endswith("/zen/go/v1/usage")
    assert read["kind"] == "json"
    assert read["windows"]["week"]["used_pct"] == 72


def test_go_zen_api_key_path_uses_ttl_cache(monkeypatch):
    """MRB #6252: Bearer zen fetch must not run on every digest fuel tick."""
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})
    monkeypatch.setenv("BOB_OPENCODE_GO_API_KEY", "FAKE_TEST_KEY")
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_S", "60")
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_WINDOWS_FIXTURE", raising=False)
    calls = {"n": 0}

    def fake_fetch(api_key, *, url=None):
        calls["n"] += 1
        return opencode_fuel.interpret_go_zen_usage_response(
            200, json.dumps(PINNED_SCHEMA), now_ms=1_700_000_000_000
        )

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    d1 = bobreport.read_local_opencode_fuel_doc(now=1000.0)
    d2 = bobreport.read_local_opencode_fuel_doc(now=1010.0)
    assert calls["n"] == 1
    assert d1["windows"]["week"]["used_pct"] == 72
    assert d2["windows"]["week"]["used_pct"] == 72
    # force bypasses TTL
    d3 = bobreport.read_local_opencode_fuel_doc(now=1015.0, force=True)
    assert calls["n"] == 2
    assert d3["windows"]["week"]["used_pct"] == 72


def test_go_zen_api_key_path_keeps_last_good_on_failure(monkeypatch):
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})
    monkeypatch.setenv("BOB_OPENCODE_GO_API_KEY", "FAKE_TEST_KEY")
    monkeypatch.setenv("BOB_OPENCODE_FUEL_CACHE_S", "1")
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    state = {"ok": True}

    def fake_fetch(api_key, *, url=None):
        if state["ok"]:
            return opencode_fuel.interpret_go_zen_usage_response(
                200, json.dumps(PINNED_SCHEMA), now_ms=1_700_000_000_000
            )
        raise RuntimeError("network down")

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    d1 = bobreport.read_local_opencode_fuel_doc(now=2000.0, force=True)
    assert d1["windows"]["week"]["used_pct"] == 72
    state["ok"] = False
    d2 = bobreport.read_local_opencode_fuel_doc(now=2100.0, force=True)
    assert d2["windows"]["week"]["used_pct"] == 72

