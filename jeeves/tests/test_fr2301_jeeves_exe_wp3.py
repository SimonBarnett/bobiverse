"""FR #2301 / WP3: Build-Jeeves + pack stage + Install NSSM cutover (Refs #1993)."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
INSTALL = ROOT / "jeeves/scripts/Install-Jeeves.ps1"
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
THIS = Path(__file__)

# Classic UTF-8-as-Latin1 mojibake prefix for em/en dash (built at runtime so the needle is not literal).
MOJIBAKE_DASH = ("\u00e2" + "\u20ac")

HIDDEN = (
    "irc_agent",
    "bobcallback",
    "gitclaim",
    "bobreport",
    "intake",
    "jeeves_locks",
    "focus_ignore",
    "chair_commands",
    "chair_health",
    "chair_oper",
    "shop_chanserv",
    "shop_listen",
    "shop_ops",
    "health",
    "queue_flow",
    "focus_seat",
    "webhook_health",
)


def test_fr2301_build_jeeves_script_hidden_imports():
    text = BUILD.read_text(encoding="utf-8")
    assert "jeeves_main.py" in text
    assert "--name', 'jeeves'" in text or '--name", "jeeves"' in text or "--name', 'jeeves'" in text
    assert "--onefile" in text
    for h in HIDDEN:
        assert h in text, h
    assert "--self-test" in text
    assert not BUILD.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr2301_pack_stages_jeeves_exe_and_skip_gate():
    text = PACK.read_text(encoding="utf-8")
    assert "SkipJeevesExe" in text
    assert "Build-Jeeves.ps1" in text
    assert r"jeeves\jeeves.exe" in text or "jeeves\\jeeves.exe" in text
    assert re.search(r"SkipJeevesExe.{0,120}SkipMsi|SkipMsi.{0,120}SkipJeevesExe", text, re.S)
    assert "2301" in text


def test_fr2301_install_nssm_cutover_and_no_second_callback():
    text = INSTALL.read_text(encoding="utf-8")
    assert r"jeeves\jeeves.exe" in text or "jeeves\\jeeves.exe" in text
    assert "$useJeevesExe" in text
    assert "--chair --http 127.0.0.1:7700" in text
    assert "--digest-home" in text
    assert "skipping Python BobCallback" in text or "skipping Python BobCallback task" in text
    assert "Start-Jeeves.ps1" in text  # legacy path kept
    assert not INSTALL.read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr2301_docs_wp3_landed_refs_living_fr():
    text = DOC.read_text(encoding="utf-8")
    assert "2301" in text
    assert "WP3" in text
    assert "never `Closes`" in text or "never Closes" in text or "Refs" in text
    assert "jeeves.exe" in text
    assert re.search(r"\|\s*WP2\s*\|[^\n]*\|\s*landed", text), "WP2 status should be landed"
    assert not re.search(r"\|\s*WP2\s*\|[^\n]*\|\s*this PR", text)


def test_fr2301_encoding_utf8_no_bom_no_mojibake():
    """Hostile: WP3 product/docs files must be UTF-8 without BOM and without classic mojibake."""
    for path in (BUILD, PACK, INSTALL, DOC, THIS):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path}"
        assert raw.endswith(b"\n"), f"missing trailing newline in {path}"
        text = raw.decode("utf-8")
        assert "\ufeff" not in text
        if path != THIS:
            assert MOJIBAKE_DASH not in text, f"mojibake in {path}"
