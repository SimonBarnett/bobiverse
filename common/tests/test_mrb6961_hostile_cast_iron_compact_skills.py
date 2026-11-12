"""MRB #6961 hostile pins for FR #6960 CAST IRON on compact skills."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILLS = [
    ROOT / "common" / ".grok" / "skills" / "change-review-findings" / "SKILL.md",
    ROOT / "common" / ".grok" / "skills" / "smallest-complete-change" / "SKILL.md",
]
MARKERS = (
    "CAST IRON RULE - HARVEST AND FILE EVERYTHING",
    "Report-BobiverseIntakeIssue.ps1",
    "Invoke-BobiverseHarvest.ps1",
    "https://bob.ntsa.uk/bob/v1/intake",
    "-Repo SimonBarnett/bobiverse",
)


def test_mrb6961_compact_skills_cast_iron_before_h1():
    for path in SKILLS:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path.name
        text = raw.decode("utf-8")
        # After frontmatter
        body = text.split("---", 2)[-1]
        iron = body.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING")
        h1 = body.index("\n# ")
        assert iron < h1, path.name
        for m in MARKERS:
            assert m in text, (path.name, m)
        assert "irc.ntsa.uk/bob/v1/intake" not in text, path.name
