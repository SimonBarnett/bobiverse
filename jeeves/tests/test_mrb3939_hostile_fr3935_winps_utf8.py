"""MRB #3939 hostile pin: FR #3935 WinPS UTF-8 skill-edit CAST IRON contiguous."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

NEEDLE = (
    "WinPS 5.1: never Get-Content -Raw (or Set-Content -Encoding utf8) round-trip of UTF-8 "
    'SKILL.md / docs; em-dashes (U+2014) mojibake. Edit with Python open(..., encoding="utf-8") '
    '/ Path.write_text(..., encoding="utf-8"); prefer ASCII --- in new prose when possible '
    "(FR #3935)."
)


def test_mrb3939_fr3935_needle_both_skills():
    for path in (MRB, FR):
        raw = path.read_bytes()
        assert raw[:3] != b"\xef\xbb\xbf", f"{path.name} BOM"
        text = raw.decode("utf-8")
        assert NEEDLE in text, f"missing NEEDLE in {path}"
        assert "Get-Content -Raw" in text
        assert "â€" not in text


def test_mrb3939_fr_skill_harvest_rule_own_bullet():
    text = FR.read_text(encoding="utf-8")
    assert "* CAST IRON harvest rule at the top:" in text
    for line in text.splitlines():
        if "WinPS UTF-8 skill edits (FR #3935)" in line:
            assert "CAST IRON harvest rule at the top" not in line
