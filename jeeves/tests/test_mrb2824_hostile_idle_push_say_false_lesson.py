"""MRB #2824 hostile: idle-push say-False lesson lives in bobiverse-jeeves-monitor."""
from __future__ import annotations

from pathlib import Path

MONITOR = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-jeeves-monitor"
    / "SKILL.md"
)
JEEVES = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-jeeves"
    / "SKILL.md"
)
HARVEST = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


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


def test_mrb2824_idle_push_say_false_in_monitor_playbook_contiguous():
    text = _utf8_no_bom(MONITOR)
    assert "Idle-push say False" in text
    assert "offer_to_idle_seats" in text
    assert "enqueue_chair_fleet_privmsg" in text
    assert "silent False" in text
    # Assign row pin + playbook bullet both present
    assert text.count("Idle-push say False") >= 2
    idx = text.index("Idle-push say False (MRB #2819 / fix #2821 / harvest-lesson #2824)")
    window = text[max(0, idx - 80) : idx + 420]
    assert "undelivered" in window
    assert "idle-after-empty" in window
    assert "rate-limit" in window
    assert "test_mrb2819_hostile_chair_outbox_say_false.py" in window
    # Still under Harvested monitor playbook (not a stray one-bullet intake section)
    section_start = text.index("## Harvested monitor playbook")
    assert "Harvested lessons (intake)" not in text[section_start:]
    assert idx > section_start
    # FR #2803 Assign context remains contiguous with idle-push pin
    assign_idx = text.index("**FR #2803:**")
    assign_window = text[assign_idx : assign_idx + 700]
    assert "Idle-push say False" in assign_window
    assert "nothing queued" in assign_window


def test_mrb2824_lesson_not_parked_in_wrong_books():
    # Product chair book may mention chair-outbox, but the folded lesson pins belong in monitor.
    harvest = _utf8_no_bom(HARVEST)
    assert "harvest-lesson #2824" not in harvest
    assert "Idle-push say False (MRB #2819 / fix #2821 / harvest-lesson #2824)" not in harvest
    jeeves = _utf8_no_bom(JEEVES)
    assert "harvest-lesson #2824" not in jeeves
