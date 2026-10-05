"""Hostile MRB #2407: FR #2406 PyInstaller UAT skill text must stay readable.

The implementer promote PR embedded C0 controls (\\x08/\\x0c/\\x07) that ate
leading letters (bob-worker -> ob-worker, free-rx -> ree-rx, reason -> eason).
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

UAT = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md"
WORKER = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
DOC = ROOT / "bob" / "docs" / "bob-worker.md"
HARVEST = ROOT / "common" / "docs" / "skill-harvest-log.md"

_CTRL = {chr(i) for i in range(32)} - {"\n", "\r", "\t"}


def _no_c0(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    bad = sorted({hex(ord(c)) for c in text if c in _CTRL})
    assert not bad, f"{path.name} has C0 controls: {bad}"


def test_uat_skill_pyinstaller_gate_phrases():
    text = UAT.read_text(encoding="utf-8")
    _no_c0(UAT)
    assert "FR #2406" in text
    assert "bob-worker.exe" in text
    assert "airc.exe" in text
    assert "free-rx" in text
    assert "reason=free" in text
    assert "_OUT_FREE_RX" in text
    assert "pyinstxtractor" in text
    assert "test_bob_worker_bored_020.py" in text
    assert "bored: free-rx matched" in text
    assert "ob-worker.exe" not in text.replace("bob-worker.exe", "")
    assert "ree-rx" not in text.replace("free-rx", "")


def test_worker_skill_pack_verify_section():
    text = WORKER.read_text(encoding="utf-8")
    _no_c0(WORKER)
    assert "## PyInstaller pack verify (FR #2406)" in text
    assert "bob-worker.exe" in text
    assert "bob_worker.pyc" in text
    assert "free-rx" in text
    assert "reason=free" in text
    assert "bored: free-rx matched" in text


def test_bob_worker_doc_fr2406_note():
    text = DOC.read_text(encoding="utf-8")
    _no_c0(DOC)
    assert "**FR #2406:**" in text
    assert "bob-worker.exe" in text
    assert "free-rx" in text
    assert "_OUT_FREE_RX" in text


def test_harvest_log_lesson_present():
    text = HARVEST.read_text(encoding="utf-8")
    # Scope to the #2406 entry only (older harvest-log rows have pre-existing C0).
    start = text.find("skill #2406")
    assert start >= 0, "missing skill #2406 harvest-log entry"
    end = text.find("\n## ", start + 1)
    section = text[start : end if end > 0 else start + 500]
    bad = sorted({hex(ord(c)) for c in section if c in _CTRL})
    assert not bad, f"#2406 harvest section has C0 controls: {bad}"
    assert "free-rx" in section
    assert "bob_worker.pyc" in section
    assert "reason=free" in section
