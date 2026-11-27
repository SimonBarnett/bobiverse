"""FR #10096: chair and webhooks are separate services."""
from __future__ import annotations

from repo_layout import ROOT

MAIN = ROOT / "common" / "scripts" / "jeeves_main.py"
INSTALL = ROOT / "jeeves" / "scripts" / "Install-Jeeves.ps1"
DOCS = ROOT / "jeeves" / "docs" / "jeeves-admin.md"


def test_fr10096_chair_only_does_not_bind_http():
    text = MAIN.read_text(encoding="utf-8")
    assert "--chair-only" in text
    assert "args.chair_only and not (args.http_only or args.http)" in text
    start = text.index("if args.chair_only and not")
    window = text[start:start + 900]
    assert "start_http_thread" not in window
    install = INSTALL.read_text(encoding="utf-8")
    assert "--chair-only" in install
    assert "$whName = 'BobWebhooks'" in install
    assert "127.0.0.1:7700" in install
    docs = DOCS.read_text(encoding="utf-8")
    assert "BobWebhooks" in docs
    assert "ircJeeves" in docs
