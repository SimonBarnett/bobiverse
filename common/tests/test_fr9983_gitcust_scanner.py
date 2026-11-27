"""FR #9983: AI-share scanner fills the gitcust store."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitcust  # noqa: E402


def test_fr9983_scan_titles(tmp_path):
    cust = tmp_path / "Northwind"
    task = cust / "SC-100 heaters"
    task.mkdir(parents=True)
    (task / "title.txt").write_text("Boiler house heaters\n", encoding="utf-8")
    (cust / "notes").mkdir()
    doc = gitcust.merge_scan(tmp_path / "home", tmp_path)
    assert any(c["name"] == "Northwind" for c in doc["customers"])
    rows = [t for t in doc["tasks"] if t["kind"] == "sc"]
    assert rows
    assert rows[0]["title"]
    assert "Boiler" in rows[0]["title"]
    served = gitcust.load_store(tmp_path / "home")
    assert served["tasks"][0]["title"]
