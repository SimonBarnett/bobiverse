"""FR #10002: xAI weekly heading drops the Cursor suffix and keeps the Grok account."""
from repo_layout import ROOT

SRC = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def test_fr10002_no_cursor_suffix():
    text = SRC.read_text(encoding="utf-8")
    fn = text.index("function Format-BobTrayXaiWeeklyRow")
    nxt = text.index("\nfunction ", fn + 10)
    body = text[fn:nxt]
    assert "FR #10002" in body
    assert "cursor api_key" not in body
    assert "cursor {0}" not in body
    assert "$parts += [string]`$acct" in body or '$parts += [string]$acct' in body
