"""MRB #6742 hostile: four shared tokens are not a twin; recent skip cites URL."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

from test_fr6741_harvest_twin_overlap import _ps_overlap

HARVEST = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
if not HARVEST.is_file():
    HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def test_four_shared_tokens_are_not_a_twin():
    existing = "alpha bravo charlie delta extra"
    new = "alpha bravo charlie delta foxtrot"
    assert not _ps_overlap(existing, new)


def test_recent_dedup_skip_cites_url():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert re.search(
        r"SKIPPED harvest recent lesson dedup[^\n]*\$recentTwinUrl",
        text,
    )
    assert "return [string]$pr.url" in text
