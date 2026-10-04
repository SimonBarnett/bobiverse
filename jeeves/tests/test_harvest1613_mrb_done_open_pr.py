"""Harvest #1613: open-PR MRB survives resync despite stale mrb_done."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves/.grok/skills/bobiverse-jeeves/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_harvest1613_jeeves_resync_open_pr():
    raw = JEEVES.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "mrb_done" in text
    assert "pr_exists" in text
    assert "1585" in text or "1613" in text


def test_harvest1613_troubleshooting_and_mrb():
    t = TROUBLE.read_text(encoding="utf-8")
    m = MRB.read_text(encoding="utf-8")
    assert not TROUBLE.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not MRB.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "mrb_done" in t and "1613" in t
    assert "mrb_done" in m and ("1585" in m or "1613" in m)


def test_harvest1613_log():
    text = LOG.read_text(encoding="utf-8")
    assert "1613" in text
    assert "<<<<<<" not in text


def test_harvest1613_files_end_with_newline():
    for p in (JEEVES, TROUBLE, MRB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
