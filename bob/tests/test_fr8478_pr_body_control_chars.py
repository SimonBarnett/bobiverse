"""FR #8478: PR body files must not contain C0 controls from escape interpretation."""

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-fr"
    / "SKILL.md"
)

_ALLOWED_C0 = {0x09, 0x0A, 0x0D}


def c0_controls(data: bytes) -> list[int]:
    """Bytes below 0x20 other than tab, LF, and CR."""
    return [b for b in data if b < 0x20 and b not in _ALLOWED_C0]


def test_fr8478_backspace_tab_bell_are_rejected():
    assert c0_controls(b"plain\nline\r\n") == []
    assert c0_controls(b"\tcode") == []
    assert 0x08 in c0_controls(b"- \x08ob/tests")
    assert 0x09 not in c0_controls(b"`\text")
    assert 0x07 in c0_controls(b"^\x07ssert")


def test_fr8478_skill_tells_seats_to_reject_c0():
    text = SKILL.read_text(encoding="utf-8")
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert c0_controls(raw) == []
    assert "FR #8478" in text
    assert "0x08" in text
    assert "0x07" in text
    assert "0x09" in text
    assert "0x0A" in text
    assert "0x0D" in text
    assert "no C0 controls" in text
