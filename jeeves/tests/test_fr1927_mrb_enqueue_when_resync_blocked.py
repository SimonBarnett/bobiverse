"""Harvest #1927: MRB enqueue playbook when resync is blocked."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
MON = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_fr1927_troubleshooting_row():
    text = _utf8_no_bom(TS)
    assert "1927" in text
    assert "enqueue_unaccepted" in text
    assert "git-claim.lock" in text
    assert "clear_seat_doing" in text


def test_fr1927_monitor_bullet():
    text = _utf8_no_bom(MON)
    assert "1927" in text
    assert "MRB" in text
    assert "gh pr list" in text or "enqueue" in text.lower()


def test_fr1927_skill_harvest_log():
    text = _utf8_no_bom(LOG)
    assert "1927" in text
    assert "enqueue_unaccepted" in text or "resync blocked" in text
