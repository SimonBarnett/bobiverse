"""FR #6442: NSSM/env settings migrate into appliance-settings.json + chair apply."""
from __future__ import annotations

import json
from pathlib import Path

import jeeves_settings as js


def test_fr6442_schema_gap_scan_empty_after_expansion():
    assert js.schema_gaps_from_source_scan() == []


def test_fr6442_former_nssm_keys_are_file_backed():
    """Secrets/knobs that lived in NSSM are inventoriable as file store (env overrides)."""
    for key in (
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "BOB_IRC_PASSWORD",
        "BOB_IRC_SASL_PASSWORD",
        "BOB_IRC_SASL_USER",
        "JEEVES_TICKET_CLOSURE_WAKE_URL",
        "JEEVES_TICKET_CLOSURE_S",
        "BOB_FUEL_CODERABBIT",
    ):
        spec = js.SCHEMA_BY_KEY[key]
        assert spec.store == "file", key


def test_fr6442_file_change_visible_source_file(tmp_path, monkeypatch):
    home = tmp_path / "jeeves-home"
    home.mkdir()
    monkeypatch.delenv("BOB_CODERABBIT_WAIT_MIN", raising=False)
    js.api_put_setting(
        home,
        client_ip="10.0.0.8",
        key="BOB_CODERABBIT_WAIT_MIN",
        value="18",
        actor="tester",
    )
    view = js.api_get_settings(home, client_ip="10.0.0.8")
    assert view["ok"] is True
    row = next(r for r in view["settings"] if r["key"] == "BOB_CODERABBIT_WAIT_MIN")
    assert row["value"] == "18"
    assert row["source"] == "file"


def test_fr6442_apply_loads_file_when_env_unset(tmp_path, monkeypatch):
    home = tmp_path / "jeeves-home"
    home.mkdir()
    monkeypatch.delenv("BOB_FUEL_CODERABBIT", raising=False)
    js.api_put_setting(
        home,
        client_ip="127.0.0.1",
        key="BOB_FUEL_CODERABBIT",
        value="1",
        actor="tester",
    )
    applied = js.apply_file_settings(home)
    assert "BOB_FUEL_CODERABBIT" in applied
    assert js._truthy(os.environ.get("BOB_FUEL_CODERABBIT") or "")


def test_fr6442_apply_env_still_overrides(tmp_path, monkeypatch):
    home = tmp_path / "jeeves-home"
    home.mkdir()
    monkeypatch.setenv("BOB_FUEL_CODERABBIT", "0")
    js.api_put_setting(
        home,
        client_ip="127.0.0.1",
        key="BOB_FUEL_CODERABBIT",
        value="1",
        actor="tester",
    )
    js.apply_file_settings(home)
    assert os.environ.get("BOB_FUEL_CODERABBIT") == "0"
    view = js.api_get_settings(home, client_ip="127.0.0.1")
    row = next(r for r in view["settings"] if r["key"] == "BOB_FUEL_CODERABBIT")
    assert row["source"] == "env"
    assert row["value"] == "0"


def test_fr6442_migrate_env_to_file_no_secret_print(tmp_path, monkeypatch, capsys):
    home = tmp_path / "jeeves-home"
    home.mkdir()
    monkeypatch.setenv("BOB_CODERABBIT_WAIT_MIN", "21")
    monkeypatch.setenv("GH_TOKEN", "ghs_FAKE_MIGRATE_SECRET_VALUE")
    out = js.migrate_nssm_env_to_file(home, actor="migrator")
    assert out["ok"] is True
    assert "BOB_CODERABBIT_WAIT_MIN" in out["migrated"]
    assert "GH_TOKEN" in out["migrated"]
    cfg = js.load_config_file(home)
    assert str(cfg.get("BOB_CODERABBIT_WAIT_MIN")) == "21"
    assert str(cfg.get("GH_TOKEN")) == "ghs_FAKE_MIGRATE_SECRET_VALUE"
    # Nothing secret on stdout/stderr from migrate itself.
    captured = capsys.readouterr()
    assert "ghs_FAKE_MIGRATE_SECRET_VALUE" not in captured.out
    assert "ghs_FAKE_MIGRATE_SECRET_VALUE" not in captured.err
    audit = (home / "settings-audit.jsonl").read_text(encoding="utf-8")
    assert "ghs_FAKE_MIGRATE_SECRET_VALUE" not in audit
    assert '"value": "set"' in audit or '"value":"set"' in audit.replace(" ", "")


def test_fr6442_docs_migration_notes():
    root = Path(__file__).resolve().parents[2]
    doc = root / "jeeves" / "docs" / "jeeves-settings-appliance.md"
    text = doc.read_text(encoding="utf-8")
    assert "FR #6442" in text
    assert "migrate" in text.lower()
    assert "appliance-settings.json" in text
    assert "NSSM" in text or "nssm" in text
    assert "secret" in text.lower()


def test_fr6442_jeeves_main_applies_on_start():
    src = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "jeeves_main.py"
    ).read_text(encoding="utf-8")
    assert "apply_file_settings" in src
    assert "jeeves_settings" in src


# import os used by apply tests
import os  # noqa: E402
