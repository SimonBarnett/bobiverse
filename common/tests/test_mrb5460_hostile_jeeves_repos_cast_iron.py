"""MRB #5460: bobiverse-jeeves-repos ships full CAST IRON before first ##."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-repos" / "SKILL.md"
MARKERS = (
    "CAST IRON RULE - HARVEST AND FILE EVERYTHING",
    "Report-BobiverseIntakeIssue.ps1",
    "Invoke-BobiverseHarvest.ps1",
    "https://bob.ntsa.uk/bob/v1/intake",
    "-Repo SimonBarnett/bobiverse",
)


def test_mrb5460_jeeves_repos_cast_iron_before_first_h2():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for mk in MARKERS:
        assert mk in text
    iron = text.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING")
    first_h2 = text.find("\n## ")
    assert iron < first_h2
    src = (ROOT / "common" / "tests" / "test_agent_layer_020.py").read_text(encoding="utf-8")
    assert "bobiverse-jeeves-repos" in src
    assert "FR #5271" in src
