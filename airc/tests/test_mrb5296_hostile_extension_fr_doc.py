"""Hostile pins for MRB #5296 airc EXTENSION Priority web FR vision doc."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

DOC = ROOT / "airc/docs/feature-request-airc-extension-priority-web-2026-10-31.md"


def test_mrb5296_extension_fr_doc_encoding_and_locks():
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    # Reject UTF-8 mojibake of em-dash / arrow / ellipsis (cp1252 misread)
    assert b"\xc3\xa2\xe2\x82\xac" not in raw
    text = raw.decode("utf-8")
    assert "\u00e2\u20ac" not in text
    assert "drafts/backlog.md" not in text
    assert "cgmpadejahkaggjpffnhaoiafbnicgpa" in text
    assert "https://clients2.google.com/service/update2/crx" in text
    assert "Priority-web-extension" in text
    assert "PriorityAirc/ExtensionAdmin" in text
    assert "update=off" in text
    assert "DONE id= exit=" in text
    assert "send_offer_payload" in text or "FR #5008" in text
    assert "#5290" in text and "#5295" in text
    # Fill-holes always after GPO (not only-on-GPO-fail)
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "always after GPO" in locked.lower() or "ALWAYS then" in text
    assert "no LGPO.exe" in locked.lower() or "no LGPO.exe" in text
