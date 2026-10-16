"""FR #4396: bob-ear info() must not UnicodeEncodeError on cp1252 stdout.

Crash-sig 0a885ea07472fa33: outbox_loop -> drain_outbox -> info() printed a
line containing U+2192 (RIGHTWARDS ARROW). Windows NSSM/console stdout often
uses cp1252 strict; print() then raises and kills the outbox thread.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import irc_agent  # noqa: E402


def test_fr4396_cp1252_rejects_arrow():
    """Document the crash codec: cp1252 cannot encode U+2192 (strict)."""
    with pytest.raises(UnicodeEncodeError):
        "\u2192".encode("cp1252")


def test_fr4396_info_survives_cp1252_stdout(monkeypatch):
    """info() must not raise when stdout encoding cannot represent the message."""
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", buf)
    # Must not raise (pre-fix: UnicodeEncodeError on arrow).
    irc_agent.info("WARN outbox preview: A \u2192 B")
    buf.flush()
    raw = buf.buffer.getvalue()
    # Replacement or ascii-safe fallback still lands something.
    assert raw
    text = raw.decode("cp1252", errors="replace")
    assert "WARN outbox preview" in text
    assert "A" in text and "B" in text


def test_fr4396_info_source_guards_encode():
    """Static pin: info() body must not be a bare print(msg) without encode guard."""
    src = (SCRIPTS / "irc_agent.py").read_text(encoding="utf-8")
    # Locate def info
    start = src.index("def info(msg: str)")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    assert "print(msg, flush=True)" not in body or "errors=" in body or "UnicodeEncodeError" in body
    assert "errors=" in body or "UnicodeEncodeError" in body or "encode(" in body
