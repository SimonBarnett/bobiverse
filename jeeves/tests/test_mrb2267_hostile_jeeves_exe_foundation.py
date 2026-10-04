"""MRB #2267 hostile: WP0/WP1 foundation must not auto-close living FR #1993."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves/docs/jeeves-exe-self-heal.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
MAIN = ROOT / "common/scripts/jeeves_main.py"
LOCKS = ROOT / "common/scripts/jeeves_locks.py"
GITCLAIM = ROOT / "common/scripts/gitclaim.py"


def test_mrb2267_living_fr_refs_not_closes_in_docs():
    text = DOC.read_text(encoding="utf-8")
    assert "Living architecture FR" in text or "living #1993" in text.lower() or "#1993" in text
    assert "never `Closes`" in text or "never Closes" in text or "Refs" in text
    assert "do not twin" in text.lower() or "do not twin FR" in text.lower()
    # Partial WPs must not claim E1–E5 done by closing the living FR.
    assert "WP0" in text and "WP1" in text and "WP2" in text


def test_mrb2267_harvest_log_keep_both_and_living_fr():
    log = LOG.read_text(encoding="utf-8")
    assert "jeeves.exe chair+HTTP foundation" in log
    assert "Hand-out empty under focus" in log  # keep-both with #2260
    assert "Living FR: #1993" in log or "living #1993" in log.lower()
    assert "never Closes" in log or "Refs only" in log
    assert "<<<<<<<" not in log


def test_mrb2267_foundation_modules_present():
    assert MAIN.is_file() and LOCKS.is_file()
    assert "enable_inproc_locks" in LOCKS.read_text(encoding="utf-8")
    assert "inproc_queue_lock" in GITCLAIM.read_text(encoding="utf-8")
    assert "FR #1993" in MAIN.read_text(encoding="utf-8")


def test_mrb2267_no_bom_on_touched_md():
    for p in (DOC, LOG):
        assert not p.read_bytes().startswith(b"\xef\xbb\xbf"), p
        assert p.read_bytes().endswith(b"\n"), p
