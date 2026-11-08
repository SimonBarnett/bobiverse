"""Service-owned xAI weekly publish. Not a tray percent patch.

The grok.com dashboard's 38% used is a different surface. These fixtures do not
seed that figure or its arithmetic complement.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import bobreport
import bobstat


def _billing(percent, period_end="2026-11-14T12:00:00Z", fetched="2026-11-08T15:10:00Z"):
    cfg = {
        "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY", "end": period_end},
    }
    if percent is not None:
        cfg["creditUsagePercent"] = percent
    else:
        cfg["prepaidBalance"] = {"val": 1}
    return json.dumps(
        {
            "ts": fetched,
            "msg": "billing: fetched credits config",
            "ctx": {"config": cfg},
        }
    )


def test_used_percent_becomes_remaining_and_keeps_source():
    now = datetime(2026, 11, 8, 15, 10, tzinfo=timezone.utc)
    reading = bobreport.parse_xai_weekly_log_text(_billing(28), now=now)
    assert reading["weekly_known"] is True
    assert reading["used_pct"] == 28
    assert reading["remaining_pct"] == 72
    assert reading["source"] == "unified.jsonl:billing:creditUsagePercent"
    assert reading["provider"] == "xai"
    assert reading["period_end"] == "2026-11-14T12:00:00Z"
    assert reading["fetched_at"] == "2026-11-08T15:10:00Z"


def test_missing_percent_is_unknown_not_zero():
    now = datetime(2026, 11, 8, 15, 10, tzinfo=timezone.utc)
    reading = bobreport.parse_xai_weekly_log_text(_billing(None), now=now)
    assert reading["weekly_known"] is False
    assert reading["remaining_pct"] is None
    assert reading["used_pct"] is None
    peer = bobreport.enrich_peer_with_xai_weekly(
        {"id": "marchhare", "pcent": {"grok-chat": 98}, "ok": True}, reading
    )
    assert peer["weekly"] is None
    assert peer["weekly_known"] is False
    assert "grok-build" not in peer["pcent"]
    assert peer["pcent"]["grok-chat"] == 98
    assert peer["xai_weekly"]["remaining_pct"] is None
    assert peer["xai_weekly"]["direction"] == "remaining"
    assert peer["xai_weekly"]["account"] is None


def test_enrich_splits_xai_remaining_from_cursor_sand():
    now = datetime(2026, 11, 8, 15, 10, tzinfo=timezone.utc)
    reading = bobreport.parse_xai_weekly_log_text(_billing(28), now=now)
    peer = bobreport.enrich_peer_with_xai_weekly(
        {"id": "marchhare", "pcent": {"grok-chat": 98}, "ok": True}, reading
    )
    assert peer["weekly"] == 72
    assert peer["pcent"]["grok-build"] == 72
    assert peer["pcent"]["grok-chat"] == 98
    meter = peer["xai_weekly"]
    assert meter["provider"] == "xai"
    assert meter["window"] == "weekly"
    assert meter["direction"] == "remaining"
    assert meter["remaining_pct"] == 72
    assert meter["used_pct"] == 28
    assert meter["source"] == "unified.jsonl:billing:creditUsagePercent"
    assert meter["fetched_at"] == "2026-11-08T15:10:00Z"
    assert meter["period_end"] == "2026-11-14T12:00:00Z"
    assert meter["account"] is None
    body = bobreport.build_peer_fuel_merge_payload(peer, "marchhare")
    assert "grok-build" in body["pcent"]
    assert body["xai_weekly"]["provider"] == "xai"
    assert "xai_weekly" in bobreport.peer_fuel_fingerprint(peer)


def test_cursor_unknown_merge_keeps_xai_meter_and_drops_sand(tmp_path: Path):
    doc = {"v": 1, "machines": {}}
    bobreport._apply_merge_payload(
        doc,
        "marchhare",
        {
            "op": "merge",
            "machine": "marchhare",
            "cursor_known": False,
            "weekly": 72,
            "weekly_known": True,
            "period_end": "2026-11-14T12:00:00Z",
            "pcent": {"grok-build": 72, "grok-chat": 98, "opencode-free": 100},
            "xai_weekly": {
                "provider": "xai",
                "direction": "remaining",
                "remaining_pct": 72,
                "used_pct": 28,
                "source": "unified.jsonl:billing:creditUsagePercent",
                "fetched_at": "2026-11-08T15:10:00Z",
                "period_end": "2026-11-14T12:00:00Z",
                "account": None,
            },
        },
    )
    ent = doc["machines"]["marchhare"]
    assert ent["cursor_known"] is False
    assert ent["pcent"]["grok-build"] == 72
    assert ent["pcent"]["opencode-free"] == 100
    assert "grok-chat" not in ent["pcent"]
    assert not ent.get("cursor_pools")
    assert ent["xai_weekly"]["source"].startswith("unified.jsonl")
    assert ent["xai_weekly"]["used_pct"] == 28
    assert ent["weekly"] == 72
    exported = bobreport.export_machine_for_tray(tmp_path, "marchhare", ent)
    assert exported["pcent"]["grok-build"] == 72
    assert "grok-chat" not in exported.get("pcent", {})
    assert exported["xai_weekly"]["fetched_at"] == "2026-11-08T15:10:00Z"
    assert exported["xai_weekly"]["period_end"] == "2026-11-14T12:00:00Z"


def test_legacy_admin_home_is_not_posted_or_cleared(tmp_path: Path):
    home = tmp_path / "Users" / "Administrator" / ".agentic-irc-bobiverse"
    home.mkdir(parents=True)
    marker = home / "digest.json"
    marker.write_text("{}\n", encoding="utf-8")
    bobstat.write_peer(
        home,
        {"ok": True, "id": "marchhare", "online": True, "weekly": 72, "pcent": {"grok-build": 72}},
    )
    called = {"n": 0}

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        called["n"] += 1
        raise AssertionError("legacy admin home must not POST")

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, "marchhare", force=True, url="https://example.test/bob/v1/report"
        )
    assert code is None
    assert called["n"] == 0
    assert marker.read_text(encoding="utf-8") == "{}\n"
    assert not (home / "digest-fuel-post-state.json").exists()
    diag = bobreport.last_fuel_publish_diag()
    assert diag["home_role"] == "legacy-admin-not-active"
    assert diag["ack"] is False
    assert diag["skipped"] == "legacy-admin-home-not-service"


def test_urlerror_records_reason_and_is_not_an_ack(tmp_path: Path):
    import urllib.error

    home = tmp_path / "svc-home"
    home.mkdir()
    bobstat.write_peer(
        home, {"ok": True, "id": "marchhare", "online": True, "status": "operational", "weekly": 10}
    )

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        raise urllib.error.URLError(OSError("timed out"))

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, "marchhare", force=True, url="https://example.test/bob/v1/report"
        )
    assert code is None
    diag = bobreport.last_fuel_publish_diag()
    assert diag["ack"] is False
    assert diag["http_status"] is None
    assert diag["error"] == "URLError"
    assert "timed out" in str(diag["reason"])
    line = bobreport.format_fuel_publish_diag(diag)
    assert "ack=false" in line
    assert "error=URLError" in line
    text = (home / "digest-fuel-publish-diag.json").read_text(encoding="utf-8")
    assert "digest-absent" not in text


def test_system_profile_weekly_log_is_not_read(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("BOB_WEEKLY_LOG", raising=False)
    monkeypatch.setenv("USERPROFILE", r"C:\Windows\system32\config\systemprofile")
    monkeypatch.delenv("HOME", raising=False)
    path, identity = bobreport.xai_weekly_log_candidate()
    assert path is None
    assert identity == "system-profile-skipped"
    assert bobreport.read_local_xai_weekly() is None
    explicit = tmp_path / "unified.jsonl"
    explicit.write_text("not-a-billing-line\n", encoding="utf-8")
    monkeypatch.setenv("BOB_WEEKLY_LOG", str(explicit))
    path2, identity2 = bobreport.xai_weekly_log_candidate()
    assert path2 == explicit
    assert identity2 == "explicit"


def test_peer_heading_names_provider_window_and_direction():
    hover = Path(__file__).resolve().parents[2] / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
    text = hover.read_text(encoding="utf-8")
    assert "function Format-BobPeerPoolHeading" in text
    assert "cursor-models', 'grok-build', 'copilot', 'grok-bot'" not in text
    watch = Path(__file__).resolve().parents[2] / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
    assert "Format-BobPeerPoolHeading" in watch.read_text(encoding="utf-8")


def test_local_system_cache_home_is_install_root_home():
    home = bobreport.resolve_ear_cache_home(
        explicit_home="",
        install_root=r"C:\ai\bob",
        local_system=True,
        userprofile=r"C:\Users\Administrator",
    )
    assert str(home).replace("/", "\\").lower().endswith("\\ai\\bob\\home")
    user = bobreport.resolve_ear_cache_home(
        explicit_home="",
        install_root=r"C:\ai\bob",
        local_system=False,
        userprofile=r"C:\Users\Administrator",
    )
    assert str(user).replace("/", "\\").lower().endswith("\\administrator\\.bobiverse")
    assert "administrator" not in str(home).lower()


def test_heartbeat_stamps_fresh_last_seen_and_logs_target(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BOB_EAR_DIGEST_FUEL_S", "30")
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    bobstat.write_peer(
        home,
        {
            "ok": True,
            "id": "marchhare",
            "online": True,
            "status": "operational",
            "weekly": 10,
            "weekly_known": True,
            "lastSeen": "2026-11-07T22:11:09Z",
            "pcent": {"grok-chat": 74},
        },
    )
    bodies: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        bodies.append(json.loads(req.data.decode("utf-8")))

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        assert (
            bobreport.publish_local_peer_fuel(
                home, "marchhare", force=False, url="https://bob.ntsa.uk/bob/v1/report", now=1_700_000_000
            )
            == 200
        )
        assert (
            bobreport.publish_local_peer_fuel(
                home, "marchhare", force=False, url="https://bob.ntsa.uk/bob/v1/report", now=1_700_000_040
            )
            == 200
        )
    assert len(bodies) == 2
    assert bodies[0]["lastSeen"] != "2026-11-07T22:11:09Z"
    assert bodies[1]["lastSeen"] != bodies[0]["lastSeen"]
    assert bodies[0]["pcent"]["grok-chat"] == 74
    diag = bobreport.last_fuel_publish_diag()
    assert diag["ack"] is True
    assert diag["http_status"] == 200
    assert diag["target_host"] == "bob.ntsa.uk"
    assert diag["target_path"] == "/bob/v1/report"
    assert diag["url_source"] == "explicit"
    line = bobreport.format_fuel_publish_diag(diag)
    assert "target_host=bob.ntsa.uk" in line
    assert "ack=true" in line
    doc = {"machines": {}}
    bobreport._apply_merge_payload(doc, "marchhare", bodies[1])
    assert doc["machines"]["marchhare"]["lastSeen"] == bodies[1]["lastSeen"]


def test_config_report_host_is_not_rewritten(tmp_path: Path, monkeypatch):
    root = tmp_path / "install"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "bobiverse.json").write_text(
        json.dumps({"reportUrl": "https://bob.ntsa.uk/bob/v1/report", "host": "irc.ntsa.uk"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(root))
    monkeypatch.delenv("BOB_REPORT_URL", raising=False)
    chosen = bobreport.resolve_fuel_report_target()
    assert chosen["ok"] is True
    assert chosen["host"] == "bob.ntsa.uk"
    assert chosen["path"] == "/bob/v1/report"
    assert chosen["source"] == "config"
    (cfg / "bobiverse.json").write_text(
        json.dumps({"reportUrl": "https://irc.ntsa.uk/bob/v1/report?token=secret"}),
        encoding="utf-8",
    )
    refused = bobreport.resolve_fuel_report_target()
    assert refused["ok"] is False
    assert refused["error"] == "query"
    assert "token" not in json.dumps(refused)
    embedded = bobreport.resolve_fuel_report_target("https://user:pw@bob.ntsa.uk/bob/v1/report")
    assert embedded["ok"] is False
    assert embedded["error"] == "userinfo"
    assert "pw" not in json.dumps(embedded)


def test_service_home_candidate_is_install_root_home(monkeypatch, tmp_path: Path):
    root = tmp_path / "ai" / "bob"
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(root))
    monkeypatch.delenv("BOB_EAR_HOME", raising=False)
    assert bobreport.service_publish_home_candidate() == root / "home"
    assert bobreport.classify_publish_home(root / "home") == "service"
    assert bobreport.classify_publish_home(tmp_path / "other") == "unlocalized"
