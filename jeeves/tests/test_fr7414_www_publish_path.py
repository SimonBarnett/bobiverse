"""FR #7414: Install-BobWebhooks publishes downloads, commands, shared CSS to IIS path."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from repo_layout import REPO

INSTALL = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
WWW = REPO / "jeeves" / "www" / "irc-ntsa"
DOCS = REPO / "jeeves" / "docs" / "webhooks.md"

PS = shutil.which("powershell.exe") or shutil.which("pwsh")
NEED_PS = __import__("pytest").mark.skipif(not PS, reason="PowerShell required")


def test_fr7414_install_script_pins_www_publish_targets():
    text = INSTALL.read_text(encoding="utf-8-sig")
    assert "site.css" in text
    assert "downloads" in text
    assert "jeeves" in text and "commands" in text
    assert "FR #7414" in text or "7414" in text
    # Rewrite must skip static /jeeves/commands (and assets) so IIS serves files.
    assert 'pattern="/jeeves/commands' in text or "jeeves/commands" in text
    assert "Copy-Item" in text


def test_fr7414_docs_note_operator_sync():
    text = DOCS.read_text(encoding="utf-8")
    assert "Install-BobWebhooks" in text
    assert "7414" in text
    assert "downloads" in text.lower()
    assert "commands" in text.lower() or "/jeeves/commands" in text
    assert "site.css" in text


@NEED_PS
def test_fr7414_install_copies_downloads_css_and_commands(tmp_path: Path):
    """Fresh copy into a temp IIS physical path includes required static assets."""
    www = tmp_path / "www-src"
    shutil.copytree(WWW, www)
    # FR-F content may not be on main yet; stage a minimal commands page for publish.
    commands = www / "jeeves" / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    (commands / "index.html").write_text(
        "<!DOCTYPE html><title>commands</title><p>!help</p>\n",
        encoding="utf-8",
    )
    assert (www / "site.css").is_file()
    assert (www / "downloads" / "index.html").is_file()

    site = tmp_path / "iis-physical"
    site.mkdir()
    # Point Install at our fixture www by invoking with PhysicalPath only and
    # temporarily swapping via a wrapper: call the script's sync by setting
    # a junction/copy beside the script is heavy; instead run Install against
    # PhysicalPath and patch www by placing fixture where the script expects.
    # Script uses Join-Path $PSScriptRoot '..\www\irc-ntsa' — so run a small
    # inline sync that mirrors FR #7414 publish rules, OR copy fixture over
    # the real www for the duration (unsafe). Prefer invoking powershell that
    # reimplements the same Copy-Item list from the script after reading it.
    #
    # Stronger: run Install-BobWebhooks.ps1 with PhysicalPath after replacing
    # www via a temporary rename of the real tree (too dangerous). Use -File
    # with env BOB_WWW_SRC if we add it; for this FR add -WwwSource param.

    args = [
        PS,
        "-NoProfile",
        "-File",
        str(INSTALL),
        "-PhysicalPath",
        str(site),
        "-Backend",
        "http://127.0.0.1:7700",
        "-WwwSource",
        str(www),
        "-PublishWww",
    ]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert (site / "site.css").is_file(), "shared CSS must be published"
    assert (site / "downloads" / "index.html").is_file(), "downloads must be published"
    assert (site / "jeeves" / "commands" / "index.html").is_file(), "commands must be published"
    cfg = (site / "web.config").read_text(encoding="utf-8")
    assert "jeeves/commands" in cfg or 'pattern="/jeeves/commands' in cfg
