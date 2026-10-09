"""FR #3803: twin-close must use exact title eq / StartsWith, never -match shared substrings."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))
from bobiverse_exact_title import (  # noqa: E402
    BANNED_SHARED_NEEDLES,
    MIN_NEEDLE_LEN,
    is_exact_harvest_twin_title,
    select_exact_title_twins,
)

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HELPER = ROOT / "common" / "scripts" / "bobiverse_exact_title.py"

# Incident corpus from MRB #3792 / FR #3803 (titles truncated the same way gh often shows).
TITLES = [
    "lesson(harvest): Product MSI Pack lessons that already live in airc-troubleshooting (or P...",
    "lesson(harvest): Airc nickserv-ok / fresh-client SASL lessons that already live in bobive...",
    "lesson(harvest): cmd: must not subprocess.run list argv: list2cmdline doubles trailing ba...",
]


def test_fr3803_shared_substring_must_not_sweep_unrelated_tips():
    """Banned shared needle alone must select zero tips (the #3792 incident class)."""
    bad = "lessons that already live"
    assert bad in BANNED_SHARED_NEEDLES or any(
        bad.lower() == b.lower() for b in BANNED_SHARED_NEEDLES
    )
    assert select_exact_title_twins(TITLES, bad) == []
    assert not is_exact_harvest_twin_title(TITLES[0], bad)
    assert not is_exact_harvest_twin_title(TITLES[1], bad)
    assert not is_exact_harvest_twin_title(TITLES[2], bad)


def test_fr3803_product_msi_pack_prefix_selects_only_that_tip():
    needle = "lesson(harvest): Product MSI Pack lessons that already live"
    assert len(needle) >= MIN_NEEDLE_LEN
    got = select_exact_title_twins(TITLES, needle)
    assert got == [TITLES[0]]
    assert TITLES[1] not in got
    assert TITLES[2] not in got


def test_fr3803_exact_equality_and_short_needle_rejected():
    full = TITLES[2]
    assert is_exact_harvest_twin_title(full, full)
    assert not is_exact_harvest_twin_title(full, "cmd:")  # too short
    assert not is_exact_harvest_twin_title(full, "list2cmdline")  # too short


def test_fr3803_skill_cast_iron_forbids_powershell_match():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3803" in text
    assert "CAST IRON twin-close filter" in text
    # Contiguous playbook: ban -match; prefer -eq / StartsWith.
    assert "PowerShell `-match`" in text or "PowerShell -match" in text
    assert "StartsWith" in text
    assert "-eq" in text or "exact title equality" in text
    assert "lessons that already live" in text
    assert "MRB #3792" in text
    assert HELPER.is_file()
