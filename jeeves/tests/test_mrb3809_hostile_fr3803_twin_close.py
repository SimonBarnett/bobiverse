"""MRB #3809 hostile: FR #3803 twin-close exact title eq / StartsWith (ban -match)."""
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
PRODUCT = ROOT / "bob" / "tests" / "test_fr3803_twin_close_exact_eq.py"

# Corpus from FR #3803 / MRB #3792 incident class.
TITLES = [
    "lesson(harvest): Product MSI Pack lessons that already live in airc-troubleshooting (or P...",
    "lesson(harvest): Airc nickserv-ok / fresh-client SASL lessons that already live in bobive...",
    "lesson(harvest): cmd: must not subprocess.run list argv: list2cmdline doubles trailing ba...",
]


def test_mrb3809_hostile_skill_forbids_match_and_shared_substring():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3803" in text
    assert "**CAST IRON twin-close filter (FR #3414" in text
    assert "PowerShell `-match`" in text or "PowerShell -match" in text
    assert "StartsWith" in text
    assert "lessons that already live" in text
    assert "MRB #3792" in text
    assert "bobiverse_exact_title.py" in text


def test_mrb3809_hostile_helper_bans_shared_needle_sweep():
    assert HELPER.is_file()
    bad = "lessons that already live"
    assert any(bad.lower() == b.lower() for b in BANNED_SHARED_NEEDLES)
    assert select_exact_title_twins(TITLES, bad) == []
    needle = "lesson(harvest): Product MSI Pack lessons that already live"
    assert len(needle) >= MIN_NEEDLE_LEN
    assert select_exact_title_twins(TITLES, needle) == [TITLES[0]]
    assert is_exact_harvest_twin_title(TITLES[2], TITLES[2])
    assert not is_exact_harvest_twin_title(TITLES[2], "cmd:")


def test_mrb3809_hostile_product_pin_present():
    assert PRODUCT.is_file()
    p = PRODUCT.read_text(encoding="utf-8")
    assert "FR #3803" in p
    assert "select_exact_title_twins" in p
    assert "lessons that already live" in p
    raw = PRODUCT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
