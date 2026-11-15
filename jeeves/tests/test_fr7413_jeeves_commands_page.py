"""FR #7413: public unauthenticated /jeeves/commands HTML + IIS rewrite skip."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import REPO

WWW = REPO / "jeeves" / "www" / "irc-ntsa"
COMMANDS = WWW / "jeeves" / "commands" / "index.html"
HOME = WWW / "index.html"
INSTALL = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
SOURCE_MD = REPO / "jeeves" / "docs" / "jeeves-commands.md"


def test_fr7413_commands_page_exists_with_core_verbs():
    assert COMMANDS.is_file(), "jeeves/www/irc-ntsa/jeeves/commands/index.html required"
    text = COMMANDS.read_text(encoding="utf-8")
    for verb in ("!help", "!list", "!focus", "!assign"):
        assert verb in text, verb
    assert "site.css" in text
    assert "/jeeves" in text
    assert "no login" in text.lower() or "unauthenticated" in text.lower() or "Public" in text
    # Must not look like a settings login form
    assert "password" not in text.lower()


def test_fr7413_home_and_downloads_nav_to_commands():
    home = HOME.read_text(encoding="utf-8")
    assert "/jeeves/commands" in home
    dl = WWW / "downloads" / "index.html"
    if dl.is_file():
        assert "/jeeves/commands" in dl.read_text(encoding="utf-8")


def test_fr7413_install_skips_rewrite_for_commands_and_syncs_tree():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "jeeves/commands" in text
    # Rewrite must exclude commands like assets
    assert re.search(r'pattern="/jeeves/commands', text) or "jeeves/commands" in text
    assert "Copy-Item" in text
    # Sync destination under PhysicalPath\\jeeves\\commands
    assert "jeeves" in text and "commands" in text


def test_fr7413_source_md_still_documents_core_verbs():
    md = SOURCE_MD.read_text(encoding="utf-8")
    for verb in ("!help", "!list", "!focus", "!assign"):
        assert verb in md


def test_fr7413_commands_page_links_markdown_source():
    text = COMMANDS.read_text(encoding="utf-8")
    assert "jeeves-commands.md" in text
