"""FR #3935: WinPS must not Get-Content -Raw round-trip UTF-8 SKILL.md (em-dash mojibake)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"

NEEDLE = (
    "WinPS 5.1: never Get-Content -Raw (or Set-Content -Encoding utf8) round-trip of UTF-8 "
    "SKILL.md / docs; em-dashes (U+2014) mojibake. Edit with Python open(..., encoding=\"utf-8\") "
    "/ Path.write_text(..., encoding=\"utf-8\"); prefer ASCII --- in new prose when possible "
    "(FR #3935)."
)


def _assert_skill(path: Path) -> None:
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", f"{path.name} must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert NEEDLE in text, f"FR #3935 CAST IRON missing from {path}"
    # reject classic UTF-8-as-cp1252 mojibake of em-dash
    assert "â€" not in text


def test_fr3935_mrb_skill_documents_winps_utf8_edit():
    _assert_skill(MRB)


def test_fr3935_fr_skill_documents_winps_utf8_edit():
    _assert_skill(FR)


def test_fr3935_python_roundtrip_preserves_emdash(tmp_path):
    sample = "CAST IRON \u2014 never mojibake\n"
    p = tmp_path / "skill.md"
    p.write_text(sample, encoding="utf-8")
    got = p.read_text(encoding="utf-8")
    assert "\u2014" in got
    assert got == sample
