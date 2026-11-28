"""FR #9995: default Weights rows are Copilot-MRB and Copilot-PR."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import models_catalog as mc  # noqa: E402


def test_defaults_are_two_copilot_rows():
    names = [a for a, _c in mc._DEFAULT_ROWS]
    assert "Copilot" not in names
    assert names[-2:] == ["Copilot-MRB", "Copilot-PR"]
    rows = mc.default_agent_rows()
    by = {r["agent"]: r for r in rows}
    assert by["Copilot-MRB"]["cli"] == "Copilot"
    assert by["Copilot-MRB"]["model"] == ""
    assert by["Copilot-PR"]["model"] == ""


def test_legacy_copilot_put_copies_model_onto_both():
    agents = [
        {"agent": a, "cli": c, "model": "", "context": "", "effort": ""}
        for a, c in mc._DEFAULT_ROWS
        if a not in mc._COPILOT_KIND_AGENTS
    ]
    agents.append({"agent": "Copilot", "cli": "Copilot", "model": "claude-haiku-4.5", "context": "", "effort": ""})
    rows, why = mc.validate_put_agents({"agents": agents})
    assert why == ""
    by = {r["agent"]: r for r in rows}
    assert by["Copilot-MRB"]["model"] == "claude-haiku-4.5"
    assert by["Copilot-PR"]["model"] == "claude-haiku-4.5"
    assert "Copilot" not in by
