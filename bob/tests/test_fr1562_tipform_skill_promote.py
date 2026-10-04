"""Harvest #1562: TipForm stale/sync playbook lives in bob skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
TROUBLE = ROOT / "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1562_bob_skill_tipform_sync():
    text = BOB.read_text(encoding="utf-8")
    assert not BOB.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Sync-BobTrayStatusWorkersFromDigest" in text
    assert "Get-BobTrayHover" in text
    assert "non-UI" in text or "SynchronizingObject" in text
    assert "1562" in text or "1553" in text


def test_fr1562_troubleshooting_row():
    text = TROUBLE.read_text(encoding="utf-8")
    assert "TipForm stale" in text or "tray-status.json" in text
    assert "1576" in text or "Sync-BobTrayStatusWorkersFromDigest" in text


def test_fr1562_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1562" in text
    assert "TipForm" in text