"""FR #5348: airc-priority-client.md must be UTF-8 without BEL/tab fence corruption."""
from __future__ import annotations

from repo_layout import ROOT

DOC = ROOT / "airc" / "docs" / "airc-priority-client.md"


def test_fr5348_no_bel_or_tab_mojibake():
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "\x07" not in text  # BEL must not eat the leading 'a' of airc
    assert "\t" not in text
    assert "\x07irc" not in text
    assert "airc/config/priority-instances.example.json" in text
    assert "airc/scripts/airc_priority.py" in text
    # Fences are real ```json / ```text, not ` + TAB + ext
    assert "```json" in text
    assert "```text" in text
    assert "`\text" not in text.replace("```text", "")
    assert "secret / token / pwd" in text
