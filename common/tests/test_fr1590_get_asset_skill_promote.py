"""Harvest #1590: Get-Asset fail-closed + Airc Fleet ServiceMode live in skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
AIRC = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1590_fleet_ops_get_asset():
    raw = FLEET.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Get-Asset" in text
    assert "download-failed" in text or "fail-closed" in text.lower() or "TimeoutSec" in text
    assert "curl" in text.lower()
    assert "$args" in text or "launchArgs" in text
    assert "1545" in text or "1561" in text


def test_fr1590_airc_fleet_servicemode():
    text = AIRC.read_text(encoding="utf-8")
    assert "ServiceMode" in text
    assert "Start-AircConsole-Fleet" in text or "Fleet wrapper" in text
    assert "launchArgs" in text or "$args" in text


def test_fr1590_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1590" in text
    assert "Get-Asset" in text or "ServiceMode" in text
    assert "<<<<<<" not in text


def test_fr1590_files_end_with_newline():
    for p in (FLEET, AIRC, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
