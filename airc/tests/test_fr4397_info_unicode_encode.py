"""FR #4397: airc info() must not UnicodeEncodeError on cp1252 stdout.

Same class as bob-ear FR #4396 (crash-sig 0a885ea07472fa33): Windows NSSM/console
stdout often uses cp1252 strict; print() of U+2192 then raises and can kill the
service thread. airc_console_service.info() had bare print(f'{ts} {msg}').
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import airc_console_service as acs  # noqa: E402


def test_fr4397_cp1252_rejects_arrow():
    """Document the crash codec: cp1252 cannot encode U+2192 (strict)."""
    with pytest.raises(UnicodeEncodeError):
        "\u2192".encode("cp1252")


def test_fr4397_info_survives_cp1252_stdout(monkeypatch):
    """info() must not raise when stdout encoding cannot represent the message."""
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", buf)
    # Must not raise (pre-fix: UnicodeEncodeError on arrow).
    acs.info("WARN preview: A \u2192 B")
    buf.flush()
    raw = buf.buffer.getvalue()
    assert raw
    text = raw.decode("cp1252", errors="replace")
    assert "WARN preview" in text
    assert "A" in text and "B" in text


def test_fr4397_info_source_guards_encode():
    """Static pin: info() body must guard UnicodeEncodeError / errors=replace."""
    src = (SCRIPTS / "airc_console_service.py").read_text(encoding="utf-8")
    start = src.index("def info(msg: str)")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    assert "UnicodeEncodeError" in body or "errors=" in body or "encode(" in body
