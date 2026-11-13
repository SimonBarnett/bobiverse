"""FR #6263: Go zen acquisition must identify failures; urllib UA must not be bare.

MarchHare after FR #6248 deploy: source=go-zen-usage with all windows unknown and
empty useful diagnostics. Same class as digest FR #6144 — default Python-urllib
User-Agent is edge-banned (Cloudflare 1010). Failed reads must stay unknown and
surface acquisition kind (auth / entitlement / blocked_1010 / rate_limited /
unavailable / malformed / missing_key / json).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import opencode_fuel

PINNED = {
    "useBalance": True,
    "rollingUsage": {"status": "ok", "usagePercent": 0, "resetInSec": 3600},
    "weeklyUsage": {"status": "ok", "usagePercent": 72, "resetInSec": 23520},
    "monthlyUsage": {"status": "ok", "usagePercent": 36, "resetInSec": 2239200},
}


def test_fr6263_fetch_sends_bobiverse_user_agent(monkeypatch):
    captured = {}

    class Resp:
        status = 200

        def read(self):
            return json.dumps(PINNED).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout=5.0):
            captured["ua"] = req.get_header("User-agent") or req.get_header("User-Agent")
            captured["auth"] = req.get_header("Authorization")
            return Resp()

    monkeypatch.setattr(
        opencode_fuel.urllib.request, "build_opener", lambda *a, **k: Opener()
    )
    read = opencode_fuel.fetch_go_zen_usage("FAKE_GO_KEY_NOT_REAL")
    assert read["kind"] == "json"
    assert captured["ua"] == bobreport.DIGEST_HTTP_USER_AGENT
    assert "Python-urllib" not in (captured["ua"] or "")
    assert captured["auth"] == "Bearer FAKE_GO_KEY_NOT_REAL"


def test_fr6263_classify_cloudflare_1010():
    body = json.dumps(
        {
            "error": 1010,
            "message": "browser_signature_banned",
            "error_code": "1010",
        }
    )
    read = opencode_fuel.interpret_go_zen_usage_response(403, body)
    assert read["kind"] == "blocked_1010"
    assert read["windows"]["week"]["status"] == "unknown"
    assert read["windows"]["week"]["used_pct"] is None


def test_fr6263_classify_429_and_5xx():
    assert opencode_fuel.interpret_go_zen_usage_response(429, "{}")["kind"] == "rate_limited"
    assert opencode_fuel.interpret_go_zen_usage_response(503, "{}")["kind"] == "unavailable"
    assert opencode_fuel.interpret_go_zen_usage_response(401, "{}")["kind"] == "auth_error"
    # plain 403 without 1010 cue stays entitlement_error
    assert (
        opencode_fuel.interpret_go_zen_usage_response(403, '{"error":"no_sub"}')["kind"]
        == "entitlement_error"
    )


def test_fr6263_request_id_1010_is_not_blocked_1010():
    # MRB #6264 / CodeRabbit: unrelated JSON field "1010" must not flip entitlement.
    body = json.dumps({"error": "no_sub", "request_id": "1010"})
    assert opencode_fuel.interpret_go_zen_usage_response(403, body)["kind"] == "entitlement_error"


def test_fr6263_html_error_1010_body_is_blocked():
    html = "<html>error code: 1010 Access denied</html>"
    assert opencode_fuel.interpret_go_zen_usage_response(403, html)["kind"] == "blocked_1010"


def test_fr6263_failed_read_stays_unknown_with_provider_read(monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_GO_API_KEY", "FAKE_GO_KEY")
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})

    def fake_fetch(api_key, *, url=None):
        return opencode_fuel.interpret_go_zen_usage_response(
            403,
            '{"error":1010,"message":"browser_signature_banned"}',
        )

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    doc = bobreport.read_local_opencode_fuel_doc(now=3000.0, force=True)
    assert doc.get("source") == opencode_fuel.GO_ZEN_USAGE_SOURCE
    assert doc.get("provider_read") == "blocked_1010"
    assert doc["windows"]["rolling"]["status"] == "unknown"
    assert doc["windows"]["week"]["used_pct"] is None
    assert "opencode-go" not in doc.get("pcent", {})
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") == "blocked_1010"
    assert acq.get("configured") is True


def _isolate_missing_opencode_key(monkeypatch) -> None:
    """FR #7067: !build runs as LocalSystem and FR #6996 reads seat auth.json.

    Isolate env + skip user-auth so missing-key pins stay missing_key.
    """
    for key in (
        "BOB_OPENCODE_GO_API_KEY",
        "BOB_OPENCODE_GO_USAGE_FIXTURE",
        "BOB_OPENCODE_FUEL_FIXTURE",
        "BOB_OPENCODE_WINDOWS_FIXTURE",
        "BOB_OPENCODE_AUTH_PATH",
        "BOB_OPENCODE_SEAT_HOME",
        "BOB_OPENCODE_KEY_LABEL",
        "BOB_GROK_WEEKLY_USER_HOME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: False)
    monkeypatch.setattr(bobreport, "_interactive_grok_user_home", lambda: None)
    monkeypatch.setattr(
        bobreport, "load_opencode_go_key_from_auth", lambda path: ("", "test-isolated")
    )


def test_fr6263_missing_key_distinct_from_provider_failure(monkeypatch):
    _isolate_missing_opencode_key(monkeypatch)
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(Path.cwd() / "no-such-install-root-6263"))
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})
    # Force helper miss. FR #6996: pretend OpenCode is installed so this
    # pin stays "no key set" rather than "not installed".
    monkeypatch.setattr(bobreport, "_resolve_opencode_fuel_helper_ps1", lambda e: None)
    monkeypatch.setattr(
        bobreport,
        "resolve_opencode_exe",
        lambda env=None: (r"C:\fake\opencode.exe", "explicit"),
    )
    doc = bobreport.read_local_opencode_fuel_doc(now=4000.0, force=True)
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") == "missing_key"
    assert acq.get("configured") is False
    # No fabricated go-zen source when key absent; FR #6301: explicit no-key state.
    assert doc.get("source") != opencode_fuel.GO_ZEN_USAGE_SOURCE
    assert doc.get("opencode_state") == bobreport.OPENCODE_NO_KEY_STATE or doc.get("source") == "no-key"
    week = (doc.get("windows") or {}).get("week") or {}
    assert week.get("error") == "no key set"


def test_fr7067_user_auth_json_masks_missing_key_without_isolation(tmp_path, monkeypatch):
    """Contrast: LocalSystem auth.json makes the 6263 pin look like a live key."""
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"opencode-go": {"apiKey": "FAKE_AUTH_JSON_KEY_NOT_REAL"}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_FUEL_FIXTURE", raising=False)
    monkeypatch.setenv("BOB_OPENCODE_AUTH_PATH", str(auth))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "no-install-7067"))
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})
    monkeypatch.setattr(bobreport, "_resolve_opencode_fuel_helper_ps1", lambda e: None)
    monkeypatch.setattr(
        bobreport,
        "resolve_opencode_exe",
        lambda env=None: (r"C:\fake\opencode.exe", "explicit"),
    )
    monkeypatch.setattr(
        opencode_fuel,
        "fetch_go_zen_usage",
        lambda *a, **k: opencode_fuel.interpret_go_zen_usage_response(
            200, json.dumps(PINNED), now_ms=1_700_000_000_000
        ),
    )
    doc = bobreport.read_local_opencode_fuel_doc(now=4100.0, force=True)
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") != "missing_key"
    assert acq.get("key_source") == "user-auth"
    assert doc.get("windows", {}).get("week", {}).get("used_pct") == 72


def test_fr6263_config_file_key_without_logging_secret(tmp_path, monkeypatch):
    install = tmp_path / "bob"
    cfg = install / "config"
    cfg.mkdir(parents=True)
    key_path = cfg / "opencode-go.apikey"
    key_path.write_text("FAKE_FILE_KEY_NOT_REAL\r\n", encoding="utf-8")
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.delenv("BOB_OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})
    calls = {}

    def fake_fetch(api_key, *, url=None):
        calls["key"] = api_key
        return opencode_fuel.interpret_go_zen_usage_response(
            200, json.dumps(PINNED), now_ms=1_700_000_000_000
        )

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    doc = bobreport.read_local_opencode_fuel_doc(now=5000.0, force=True)
    assert calls["key"] == "FAKE_FILE_KEY_NOT_REAL"
    assert doc["windows"]["week"]["used_pct"] == 72
    acq = bobreport.last_opencode_acquisition()
    assert acq.get("kind") == "json"
    assert acq.get("key_source") == "config-file"
    # Never retain secret material in acquisition diag
    blob = json.dumps(acq)
    assert "FAKE_FILE_KEY" not in blob


def test_fr6263_publish_diag_surfaces_opencode_acquisition(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    mid = "marchhare"
    import bobstat

    bobstat.write_peer(
        home,
        {"id": mid, "ok": True, "pcent": {"grok-chat": 10}, "lastSeen": "2026-11-08T21:00:00Z"},
    )
    monkeypatch.setenv("BOB_OPENCODE_GO_API_KEY", "FAKE_GO_KEY")
    monkeypatch.delenv("BOB_OPENCODE_GO_USAGE_FIXTURE", raising=False)
    bobreport._opencode_fuel_cache.clear()
    bobreport._opencode_fuel_cache.update({"at": 0.0, "doc": {}})

    def fake_fetch(api_key, *, url=None):
        return opencode_fuel.interpret_go_zen_usage_response(
            403, '{"error":1010,"message":"browser_signature_banned"}'
        )

    monkeypatch.setattr(opencode_fuel, "fetch_go_zen_usage", fake_fetch)
    monkeypatch.setattr(
        bobreport,
        "resolve_fuel_report_target",
        lambda url=None: {
            "ok": True,
            "url": "https://bob.ntsa.uk/bob/v1/report",
            "host": "bob.ntsa.uk",
            "path": "/bob/v1/report",
            "source": "test",
        },
    )
    monkeypatch.setattr(bobreport, "post_report_json", lambda *a, **k: 204)
    monkeypatch.setattr(bobreport, "classify_publish_home", lambda h: "service")
    code = bobreport.publish_local_peer_fuel(home, mid, force=True, now=6000.0)
    assert code == 204
    diag = bobreport.last_fuel_publish_diag()
    assert diag.get("opencode_acquisition") == "blocked_1010"
    assert diag.get("opencode_source") == opencode_fuel.GO_ZEN_USAGE_SOURCE
    line = bobreport.format_fuel_publish_diag(diag)
    assert "opencode_acquisition=blocked_1010" in line
    assert "opencode_source=go-zen-usage" in line


def test_fr6263_frozen_overlay_allowlists_opencode_fuel():
    import irc_agent

    assert "opencode_fuel" in irc_agent.FROZEN_SCRIPT_OVERLAY
    assert "bobreport" in irc_agent.FROZEN_SCRIPT_OVERLAY
    assert irc_agent.OPENCODE_FUEL_OVERLAY_MARKER == "GO_ZEN_USAGE_USER_AGENT"
    assert hasattr(opencode_fuel, "GO_ZEN_USAGE_USER_AGENT")
    assert opencode_fuel.GO_ZEN_USAGE_USER_AGENT == bobreport.DIGEST_HTTP_USER_AGENT
    # Marker must appear in the on-disk module so frozen overlay accepts the hotpatch.
    src = Path(opencode_fuel.__file__).read_text(encoding="utf-8")
    assert irc_agent.OPENCODE_FUEL_OVERLAY_MARKER in src
