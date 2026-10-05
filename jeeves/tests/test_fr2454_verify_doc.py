"""FR #2454: verification snapshot doc exists with method + gap notes."""
from __future__ import annotations

from repo_layout import ROOT

DOC = ROOT / "jeeves/docs/empty-offer-verify-2454.md"
PLAY = ROOT / "jeeves/docs/empty-offer-playbook.md"


def test_fr2454_verify_doc_has_snapshot_and_method():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "FR #2454",
        "unaccepted",
        "require_machine",
        "2455",
        "2449",
        "Invoke-RestMethod",
        "irc.ntsa.uk/bob/v1/report",
        "#2450",
    ):
        assert needle in text, needle
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")


def test_fr2454_playbook_links_verify_doc():
    text = PLAY.read_text(encoding="utf-8")
    assert "empty-offer-verify-2454" in text or "2454" in text
