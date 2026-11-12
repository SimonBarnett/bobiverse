"""MRB #6792: hostile checks for FR-10 appliance operator doc (UTF-8, URL, hosts)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves" / "docs" / "jeeves-settings-appliance.md"


def test_mrb6792_doc_utf8_no_bom():
    raw = DOC.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    DOC.read_text(encoding="utf-8")


def test_mrb6792_no_browser_url_with_port_7701():
    text = DOC.read_text(encoding="utf-8")
    assert "https://jeeves.ntsa.uk/" in text
    assert "https://jeeves.ntsa.uk:7701" not in text
    assert "http://jeeves.ntsa.uk:7701" not in text
    assert "http://127.0.0.1:7701/" not in text
    # Backend port may be named; operators must not be told to browse it.
    assert "Do not browse `:7701`" in text or "operators do not browse this port" in text.lower()


def test_mrb6792_each_public_host_refused_on_its_own():
    text = DOC.read_text(encoding="utf-8").lower()
    assert "bob.ntsa.uk" in text
    assert "irc.ntsa.uk" in text
    bob_ok = "do **not** front it via `bob.ntsa.uk`" in text or (
        "never" in text and "bob.ntsa.uk" in text
    )
    irc_ok = "do **not** front it via `irc.ntsa.uk`" in text or (
        "never" in text and "irc.ntsa.uk" in text
    )
    assert bob_ok
    assert irc_ok
    # One never + one host must not satisfy the other host.
    fake = "never publish on bob.ntsa.uk. irc.ntsa.uk is the public front."
    assert "do **not** front it via `irc.ntsa.uk`" not in fake
    assert not (
        "irc.ntsa.uk" in fake
        and "never" in fake
        and "do **not** front it via `irc.ntsa.uk`" in fake
    )
