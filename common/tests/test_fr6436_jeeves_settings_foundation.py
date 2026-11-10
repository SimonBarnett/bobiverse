"""FR #6436 foundation: LAN gate, schema, secrets, backup/audit/rollback."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_settings as js


def test_fr6436_schema_covers_fuel_and_chair_env_keys():
    """Every setting the foundation inventories must appear in the schema."""
    keys = {e.key for e in js.SCHEMA}
    for required in (
        "BOB_FUEL_CODERABBIT",
        "BOB_CODERABBIT_WAIT_MIN",
        "BOB_FUEL_COPILOT",
        "BOB_FUEL_FLEET",
        "BOB_DIGEST_HOME",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "BOB_IRC_PASSWORD",
        "BOB_IRC_SASL_PASSWORD",
    ):
        assert required in keys, f"missing schema entry for {required}"


def test_fr6436_schema_scan_fails_when_new_read_missing(tmp_path, monkeypatch):
    """A scanned BOB_/JEEVES_ environ.get that is not in SCHEMA is a gap."""
    src = tmp_path / "fake_chair.py"
    src.write_text(
        'import os\nos.environ.get("BOB_BRAND_NEW_SETTING")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(js, "SCAN_ROOTS", (src,))
    missing = js.schema_gaps_from_source_scan()
    assert "BOB_BRAND_NEW_SETTING" in missing


def test_fr6436_live_source_scan_has_no_schema_gaps():
    """Acceptance: every scanned chair environ.get is in SCHEMA or allowlist."""
    assert js.schema_gaps_from_source_scan() == []


def test_fr6436_non_lan_source_rejected():
    assert js.is_rfc1918("10.0.0.5") is True
    assert js.is_rfc1918("192.168.1.10") is True
    assert js.is_rfc1918("172.16.0.1") is True
    assert js.is_rfc1918("8.8.8.8") is False
    assert js.is_rfc1918("1.1.1.1") is False
    assert js.is_rfc1918("127.0.0.1") is True  # loopback allowed for local admin
    assert js.reject_non_lan("203.0.113.9") == "forbidden: non-LAN source"
    assert js.reject_non_lan("10.1.2.3") is None


def test_fr6436_secrets_never_returned_by_api(tmp_path, monkeypatch):
    home = tmp_path / "jeeves-home"
    home.mkdir()
    monkeypatch.setenv("GH_TOKEN", "ghs_FAKESECRET_SHOULD_NOT_LEAK")
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "1")
    view = js.api_get_settings(home, client_ip="10.0.0.8")
    assert view["ok"] is True
    blob = json.dumps(view)
    assert "ghs_FAKESECRET" not in blob
    assert "SHOULD_NOT_LEAK" not in blob
    secrets = [r for r in view["settings"] if r["key"] == "GH_TOKEN"]
    assert secrets and secrets[0]["value"] in ("set", "unset")
    fuel = [r for r in view["settings"] if r["key"] == "BOB_FUEL_CODERABBIT"]
    assert fuel and fuel[0]["value"] == "1"


def test_fr6436_invalid_rejected_backup_audit_rollback(tmp_path):
    home = tmp_path / "jeeves-home"
    home.mkdir()
    bad = js.api_put_setting(
        home,
        client_ip="10.0.0.8",
        key="BOB_CODERABBIT_WAIT_MIN",
        value="not-a-number",
        actor="tester",
    )
    assert bad["ok"] is False
    assert "invalid" in bad["error"].lower()

    ok = js.api_put_setting(
        home,
        client_ip="10.0.0.8",
        key="BOB_CODERABBIT_WAIT_MIN",
        value="12",
        actor="tester",
    )
    assert ok["ok"] is True
    backups = list((home / "settings-backups").glob("*.json"))
    assert backups, "change must create a timestamped backup"
    audit = (home / "settings-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert audit, "change must append an audit row"
    last = json.loads(audit[-1])
    assert last["key"] == "BOB_CODERABBIT_WAIT_MIN"
    assert last["actor"] == "tester"

    # Change again then roll back to previous backup.
    js.api_put_setting(
        home,
        client_ip="10.0.0.8",
        key="BOB_CODERABBIT_WAIT_MIN",
        value="20",
        actor="tester",
    )
    rb = js.api_rollback(home, client_ip="10.0.0.8", backup_id=ok["backup_id"], actor="tester")
    assert rb["ok"] is True
    cur = js.load_config_file(home)
    assert str(cur.get("BOB_CODERABBIT_WAIT_MIN")) == "12"


def test_fr6436_non_lan_api_forbidden(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    view = js.api_get_settings(home, client_ip="8.8.8.8")
    assert view["ok"] is False
    assert view["error"].startswith("forbidden")


def test_fr6436_docs_describe_internal_dns_and_reach():
    root = Path(__file__).resolve().parents[2]
    doc = root / "jeeves" / "docs" / "jeeves-settings-appliance.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "jeeves.ntsa.uk" in text
    assert "RFC1918" in text or "RFC 1918" in text or "10." in text
    assert "bob.ntsa.uk" in text  # must say never expose via public host
    assert "internal dns" in text.lower()
    assert b"\xef\xbb\xbf" not in doc.read_bytes()[:4]


def test_fr6436_vision_locks_appliance_foundation():
    vision = Path(__file__).resolve().parents[2] / "jeeves" / "VISION.md"
    text = vision.read_text(encoding="utf-8")
    assert "FR #6436" in text
    assert "jeeves.ntsa.uk" in text
    assert "appliance" in text.lower()
