"""MRB #6562 hostile: FR4522 ledger fixtures mark chair via BOB_HOME under suite."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "jeeves" / "tests" / "test_fr4522_merge_on_green_ledger_fleet_root.py"


def test_mrb6562_fr4522_homes_sets_bob_home_and_parametrises_suite():
    text = SRC.read_text(encoding="utf-8")
    assert "def _homes(" in text
    assert 'monkeypatch.setenv("BOB_HOME", str(config_home))' in text
    assert 'monkeypatch.setenv("BOB_DIGEST_HOME", str(fleet_root))' in text
    assert '@pytest.mark.parametrize("suite_mode"' in text
    assert 'assert gitclaim.queue_path(config_home) == fleet_root / "queue.json"' in text
    # Offline resync: checks present so fetch_pr_state stays unused
    assert '"checks": "pending"' in text
    assert "fetch_pr_state must not be called" in text
    assert not SRC.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6562_fleet_digest_home_chair_redirect_under_suite(tmp_path, monkeypatch):
    import bobreport

    config_home = tmp_path / "jeeves-config"
    fleet_root = tmp_path / "bobiverse-fleet"
    config_home.mkdir()
    fleet_root.mkdir()
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(fleet_root))
    # Without BOB_HOME, suite mode keeps tmp home local (FR #6523).
    monkeypatch.delenv("BOB_HOME", raising=False)
    assert bobreport.fleet_digest_home(config_home) == config_home
    # With BOB_HOME=config_home, chair redirect to fleet root still applies (FR #69/#4522).
    monkeypatch.setenv("BOB_HOME", str(config_home))
    assert bobreport.fleet_digest_home(config_home) == fleet_root
