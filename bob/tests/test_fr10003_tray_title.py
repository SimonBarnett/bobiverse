"""FR #10003: tray title is Bobiverse #<machine>."""
from repo_layout import ROOT

SRC = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def test_fr10003_title_format():
    text = SRC.read_text(encoding="utf-8")
    fn = text.index("function Get-BobTrayTitle")
    body = text[fn:fn + 800]
    assert "Bobiverse #{0}" in body
    assert "#Bobiverse ({0})" not in body
    assert "FR #10003" in body
    assert "this-machine" in body
