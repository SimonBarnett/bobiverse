"""FR #9996: job kind selects Copilot-MRB or Copilot-PR."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import copilot_dispatch as cd  # noqa: E402


def test_kind_agent_names():
    assert cd.copilot_agent_for_kind("MRB") == "Copilot-MRB"
    assert cd.copilot_agent_for_kind("FIX") == "Copilot-MRB"
    assert cd.copilot_agent_for_kind("FR") == "Copilot-PR"
    assert cd.copilot_agent_for_kind("FIX") != "Copilot-PR"
    assert cd.copilot_agent_for_kind("FR") != "Copilot-MRB"


def test_build_task_body_omits_empty_model(tmp_path, monkeypatch):
    monkeypatch.setattr(cd, "resolve_copilot_model", lambda **_k: "")
    body = cd.build_task_body({"task": "FR", "repo": "o/r", "id": "1"}, home=tmp_path)
    assert "model" not in body
