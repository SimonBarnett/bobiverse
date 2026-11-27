"""FR #10001: Cursor credential helper stays on this machine and does not emit the key."""
from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1]
    / "tray"
    / "src"
    / "Public"
    / "Resolve-BobCursorSeatCredential.ps1"
)


def test_resolver_does_not_return_or_log_the_key():
    text = SRC.read_text(encoding="utf-8")
    assert "FR #10001" in text
    assert "CURSOR_API_KEY" in text
    assert "HasLocalKey" in text
    assert "Write-Host" not in text
    assert "local-env" in text
    tail = text.split("[pscustomobject]", 1)[1]
    assert "$local" not in tail
