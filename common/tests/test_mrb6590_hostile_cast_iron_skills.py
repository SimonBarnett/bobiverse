"""MRB #6590 hostile pins for FR #6584 skill CAST IRON / frontmatter restore.

Pins that product PR #6590 landed on main:
- bob-setup-opencode CAST IRON intake host is bob.ntsa.uk (FR #5272), not irc.ntsa.uk
- common/.grok/skills/bobiverse-build has YAML frontmatter + CAST IRON RULE_MARKERS
"""
from __future__ import annotations

import re

from repo_layout import ROOT

OPENCODE = ROOT / "bob" / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md"
COMMON_BUILD = ROOT / "common" / ".grok" / "skills" / "bobiverse-build" / "SKILL.md"
RULE_MARKERS = (
    "CAST IRON RULE - HARVEST AND FILE EVERYTHING",
    "Report-BobiverseIntakeIssue.ps1",
    "Invoke-BobiverseHarvest.ps1",
    "https://bob.ntsa.uk/bob/v1/intake",
    "-Repo SimonBarnett/bobiverse",
)


def test_mrb6590_opencode_cast_iron_intake_host():
    raw = OPENCODE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "https://bob.ntsa.uk/bob/v1/intake" in t
    assert "irc.ntsa.uk/bob/v1/intake" not in t
    iron = t.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING")
    first_h2 = t.find("\n## ")
    assert iron < (first_h2 if first_h2 >= 0 else 10**9)


def test_mrb6590_common_bobiverse_build_frontmatter_and_cast_iron():
    raw = COMMON_BUILD.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8").replace("\r\n", "\n")
    m = re.match(r"---\nname: (\S+)\ndescription: >\n  .+\n---\n", t, re.S)
    assert m, "common bobiverse-build missing YAML frontmatter"
    assert m.group(1) == "bobiverse-build"
    for mk in RULE_MARKERS:
        assert mk in t, mk
    iron = t.index("CAST IRON RULE - HARVEST AND FILE EVERYTHING")
    first_h2 = t.find("\n## ")
    assert iron < (first_h2 if first_h2 >= 0 else 10**9)
