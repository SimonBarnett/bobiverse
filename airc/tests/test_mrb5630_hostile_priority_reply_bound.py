"""MRB #5630 hostile pins for FR #5616 PRIORITY IRC reply bound."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_priority as ap


def test_mrb5630_password_refused_not_redacted_as_unsafe():
    # Key-shaped redact must not swallow error codes containing "password".
    out, code = ap.format_bounded_priority_out(
        "aabbccdd",
        {"ok": False, "error": "password-refused", "action": "walk"},
        2,
    )
    assert code == 2
    assert "password-refused" in out
    assert "redacted-unsafe-payload" not in out
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES


def test_mrb5630_never_character_slices_json():
    src = Path(ap.__file__).read_text(encoding="utf-8")
    assert "format_bounded_priority_out" in src
    assert "reply-too-large" in src
    # Old prepare path sliced with [:IRC_SAFE_PAYLOAD] --- must stay gone from priority framing.
    cons = Path(ac.__file__).read_text(encoding="utf-8")
    assert "format_bounded_priority_out" in cons
    assert 'out id={jid} seq=1 {blob}"[:IRC_SAFE_PAYLOAD]' not in cons


def test_mrb5630_docs_pin_350_and_reply_too_large():
    root = Path(ap.__file__).resolve().parents[1]
    docs = (root / "docs" / "airc-priority-client.md").read_text(encoding="utf-8")
    assert "350 UTF-8 bytes" in docs or "350" in docs
    assert "reply-too-large" in docs
    assert ap.PRIORITY_REPLY_MAX_BYTES == ac.IRC_SAFE_PAYLOAD == 350

def test_mrb5630_file_is_utf8_no_bom():
    assert not Path(__file__).read_bytes().startswith(b"\xef\xbb\xbf")
