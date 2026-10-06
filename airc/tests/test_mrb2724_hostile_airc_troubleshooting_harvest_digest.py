"""MRB #2724 hostile: airc-troubleshooting harvest digest (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIRC = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
AUDIT = ROOT / "common" / "docs" / "harvest-lessons-audit-2026-10-06.md"


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


def test_mrb2724_digest_section_present():
    text = _utf8_no_bom(AIRC)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2724_console_job_protocol():
    text = _utf8_no_bom(AIRC)
    assert "Console job protocol" in text
    idx = text.index("Console job protocol")
    window = text[idx : idx + 900]
    assert "STATUS" in window
    assert "out id=" in window or "DONE id=" in window
    assert "airc-replies.jsonl" in window or "ReplyFile" in window
    assert "Heard:" in window
    assert "@(" in window or "@'" in window or '@"' in window
    assert "msiexec" in window
    assert "ConnectionError" in window or "reconnect" in window


def test_mrb2724_audit_table_path_present():
    text = _utf8_no_bom(AIRC)
    assert "harvest-lessons-audit-2026-10-06.md" in text
    assert AUDIT.is_file(), AUDIT


def test_mrb2724_digest_bullets_complete_lines():
    text = _utf8_no_bom(AIRC)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    chunk = text[start:]
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 1
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()
