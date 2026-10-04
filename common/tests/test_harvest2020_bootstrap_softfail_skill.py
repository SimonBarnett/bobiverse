"""Harvest #2020: fleet-ops documents MSI Node soft-fail under SYSTEM (FR #1825)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest2020_fleet_ops_bootstrap_row():
    text = OPS.read_text(encoding="utf-8")
    assert not OPS.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "1825" in text
    assert "nodejs.org" in text
    assert "1603" in text
    assert "WindowsApps" in text or "winget" in text.lower()
    assert "soft-fail" in text.lower() or "WARN" in text
    assert "\n<<<<<<<" not in text


def test_harvest2020_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "2020" in text or "1825" in text
    assert "nodejs.org" in text or "soft-fail" in text.lower()
    assert "bobiverse-fleet-ops" in text
    assert "\n<<<<<<<" not in text


def test_harvest2020_files_end_with_newline():
    for p in (OPS, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
