"""FR #9984: periodic updater invokes the scanner."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitcust  # noqa: E402


def test_fr9984_updater_interval_and_scan(tmp_path, monkeypatch):
    monkeypatch.delenv("GITCUST_UPDATE_S", raising=False)
    assert gitcust.updater_interval_s() == 3600
    monkeypatch.setenv("GITCUST_UPDATE_S", "30")
    assert gitcust.updater_interval_s() == 60
    monkeypatch.setenv("GITCUST_UPDATE_S", "120")
    assert gitcust.updater_interval_s() == 120
    (tmp_path / "Acme" / "WBS-9 roof").mkdir(parents=True)
    home = tmp_path / "home"
    doc = gitcust.run_updater(home, tmp_path)
    assert any(t["kind"] == "wbs" and t["title"] for t in doc["tasks"])
    docs = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "GITCUST_UPDATE_S" in docs
