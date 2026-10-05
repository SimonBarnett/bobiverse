"""Hostile MRB #2501: no Unicode punctuation; $HomePath + Alias Home; Parser::ParseFile OK."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "airc" / "scripts" / "Install-AircConsole.ps1"


def test_hostile_no_emdash_ellipsis_or_curly_quotes():
    text = SCRIPT.read_text(encoding="utf-8")
    banned = ("\u2014", "\u2013", "\u2026", "\u201c", "\u201d", "\u2018", "\u2019", "\ufeff")
    for ch in banned:
        assert ch not in text, f"banned char U+{ord(ch):04X} still present"


def test_hostile_resolve_uses_homepath_not_home_param():
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("function Resolve-AircSafeConsoleHome")
    block = text[start : start + 1200]
    assert "$HomePath" in block
    assert "[string]$Home," not in block
    assert "Alias('Home')" in block or 'Alias("Home")' in block
    assert "Test-AircDefaultProfileHome -Path $HomePath" in block


def test_hostile_author_parse_gate_present():
    gate = (ROOT / "airc" / "tests" / "test_fr2499_install_airc_console_parse.py").read_text(
        encoding="utf-8"
    )
    assert "Parser]::ParseFile" in gate
    assert "PARSE_OK" in gate
