"""Harvest #1711: agent-folder path rewrite lookbehind + Pack BOM."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1711_fleet_ops_path_rewrite():
    text = FLEET.read_text(encoding="utf-8")
    assert "Sync-BobiverseAgentFolders" in text or "lookbehind" in text
    assert "1704" in text or "1711" in text
    assert "scripts" in text


def test_fr1711_fleet_ops_pack_bom():
    text = FLEET.read_text(encoding="utf-8")
    assert "BOM" in text
    assert "Pack-BobiverseRelease" in text or "double-encoded" in text.lower() or "c3af" in text.lower()


def test_fr1711_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1711" in text
    assert "<<<<<<" not in text


def test_fr1711_files_end_with_newline():
    for p in (FLEET, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
