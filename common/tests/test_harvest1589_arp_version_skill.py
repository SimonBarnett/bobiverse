"""Harvest #1589: Sync ARP DisplayVersion is VERSION truth after MSI."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_harvest1589_fleet_ops_arp_version_truth():
    text = OPS.read_text(encoding="utf-8")
    _no_bom(OPS)
    assert "ARP" in text and "DisplayVersion" in text
    assert "1589" in text or "1565" in text
    assert "ArpVersionOverride" in text
    assert "Sync-BobiverseFromRepo" in text or "Sync" in text
    assert "InstallRoot" in text and "clobber" in text.lower()
    assert "VERSION truth" in text


def test_harvest1589_known_failure_and_harvested_rule():
    text = OPS.read_text(encoding="utf-8")
    assert "InstallRoot `VERSION` jumps after sync" in text or "disagrees with ARP" in text
    assert "After MSI, treat ARP" in text or "ARP `DisplayVersion` as VERSION truth" in text


def test_harvest1589_log():
    text = LOG.read_text(encoding="utf-8")
    _no_bom(LOG)
    assert "#1589" in text
    assert "ARP" in text or "DisplayVersion" in text
    assert "ArpVersionOverride" in text or "clone" in text.lower()
