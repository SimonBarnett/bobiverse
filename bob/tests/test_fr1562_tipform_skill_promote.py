"""Harvest #1562: TipForm stale/sync playbook lives in bob skills."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOB = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
TROUBLE = ROOT / "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1562_bob_skill_tipform_sync():
    raw = BOB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Sync-BobTrayStatusWorkersFromDigest" in text
    assert "Get-BobTrayHover" in text
    assert "non-UI" in text or "SynchronizingObject" in text
    assert "1562" in text or "1553" in text
    assert ".work" in text and ".working_on" in text
    assert "Start-BobCallbackSupervised" in text


def test_fr1562_troubleshooting_row():
    raw = TROUBLE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "TipForm stale" in text or "tray-status.json" in text
    assert "1576" in text or "Sync-BobTrayStatusWorkersFromDigest" in text
    assert "worker_list" in text or "working_on" in text


def test_fr1562_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1562" in text
    assert "TipForm" in text


def test_fr1562_files_end_with_newline():
    for p in (BOB, TROUBLE, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
