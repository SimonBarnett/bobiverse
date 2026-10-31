"""FR #5289: Playwright Priority path is follow-on design, not MVP."""
from __future__ import annotations

from repo_layout import ROOT

NOTE = ROOT / "airc/docs/feature-request-airc-priority-playwright-2026-10-31.md"
PARENT = ROOT / "airc/docs/feature-request-airc-priority-client-2026-10-31.md"


def test_fr5289_design_note_out_of_mvp():
    raw = NOTE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    t = raw.decode("utf-8")
    assert "\u2014" not in t
    assert "LOCKED" in t
    assert "Primary" in t and "service" in t.lower()
    assert "Playwright" in t
    assert "out of mvp" in t.lower() or "follow-on" in t.lower()
    assert "S1" in t and "S6" in t
    assert "do not block" in t.lower() or "must not block" in t.lower()
    assert "airc-owned" in t.lower() or "service-owned" in t.lower()
    assert "drop" in t.lower()
    assert "password=" not in t.lower()
    assert "5289" in t or "FR-H" in t


def test_fr5289_parent_points_at_followon():
    t = PARENT.read_text(encoding="utf-8")
    assert "5289" in t
    assert "Playwright" in t
    assert "out of mvp" in t.lower()
