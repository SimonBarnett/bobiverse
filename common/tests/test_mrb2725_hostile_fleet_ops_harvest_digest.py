"""MRB #2725 hostile: fleet-ops harvest digest lessons (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
AUDIT = ROOT / "common" / "docs" / "harvest-lessons-audit-2026-10-06.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2725_digest_section_present():
    text = _utf8_no_bom(OPS)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2725_winps_strictmode():
    text = _utf8_no_bom(OPS)
    assert "WinPS 5.1 / StrictMode" in text
    idx = text.index("WinPS 5.1 / StrictMode")
    window = text[idx : idx + 800]
    assert "PSObject.Properties" in window
    assert "UTF8Encoding" in window or "Set-Content -Encoding utf8" in window
    assert "$Home" in window or "$args" in window
    assert "Start-Process" in window or "--root" in window


def test_mrb2725_msi_nssm_release():
    text = _utf8_no_bom(OPS)
    assert "MSI / NSSM / release" in text
    idx = text.index("MSI / NSSM / release")
    window = text[idx : idx + 800]
    assert "Assert-BobiverseReleaseAssets" in window or "re-Pack" in window
    assert "AppExit" in window or "NSSM" in window
    assert "VERSION" in window or "ARP" in window


def test_mrb2725_crash_reporting():
    text = _utf8_no_bom(OPS)
    assert "Crash reporting" in text
    idx = text.index("Crash reporting")
    window = text[idx : idx + 600]
    assert "do-not-file" in window or "probe-shape-only" in window or "exe=probe" in window
    assert "LOCALAPPDATA" in window or "spool" in window
    assert "crash:" in window or "RETEST" in window


def test_mrb2725_audit_table_path_present():
    text = _utf8_no_bom(OPS)
    assert "harvest-lessons-audit-2026-10-06.md" in text
    assert AUDIT.is_file(), AUDIT


def test_mrb2725_digest_bullets_complete_lines():
    text = _utf8_no_bom(OPS)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 3
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()
