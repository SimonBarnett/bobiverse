"""FR #10241: FR job must reuse an existing PR on the branch instead of a duplicate gh pr create."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FR = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


def _text() -> str:
    raw = FR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), FR
    assert raw.endswith(b"\n"), FR
    return raw.decode("utf-8")


def test_fr10241_reuse_section_present():
    text = _text()
    assert "## Reuse an existing PR on the branch (FR #10241)" in text


def test_fr10241_checks_head_before_create():
    text = _text()
    idx = text.index("## Reuse an existing PR on the branch (FR #10241)")
    window = text[idx : idx + 1500]
    assert "gh pr list" in window
    assert "--head" in window
    assert "--state all" in window
    # The lookup must come before the create step (the DONE URL section runs gh pr create).
    create_idx = text.index("## DONE URL - capture `gh pr create` output (FR #108)")
    assert idx < create_idx
    assert "gh pr list" in text[idx:create_idx]


def test_fr10241_open_pr_is_reused_not_duplicated():
    text = _text()
    idx = text.index("## Reuse an existing PR on the branch (FR #10241)")
    window = text[idx : idx + 1500]
    assert "OPEN" in window
    assert "Never open a second PR" in window or "never open a second PR" in window.lower()
    assert "gh pr ready" in window
    assert "DONE" in window


def test_fr10241_evidence_reference_present():
    text = _text()
    idx = text.index("## Reuse an existing PR on the branch (FR #10241)")
    window = text[idx : idx + 1500]
    assert "#10105" in window or "#10240" in window
