# -*- coding: utf-8 -*-
"""FR #8205: bob-ear info() must not die on OSError ENOSPC (disk full stdout).

Crash-sig 2852879cc3d3bbdc on marchhare: outbox/_run thread called info() while
the log volume was full; print(..., flush=True) raised OSError errno 28 and
killed the ear thread.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import irc_agent  # noqa: E402


class _EnospcStdout(io.StringIO):
    def write(self, s):  # noqa: ANN001
        raise OSError(28, "No space left on device")

    def flush(self):
        raise OSError(28, "No space left on device")


def test_fr8205_is_enospc_errno_and_winerror():
    assert irc_agent.is_enospc(OSError(28, "No space left on device"))
    e = OSError("disk problem")
    e.winerror = 112
    assert irc_agent.is_enospc(e)
    assert not irc_agent.is_enospc(OSError(2, "No such file"))


def test_fr8205_info_survives_enospc_stdout(monkeypatch):
    """info() must not raise when stdout write hits ENOSPC."""
    monkeypatch.setattr(sys, "stdout", _EnospcStdout())
    irc_agent.info("WARN ear still alive under disk full")


def test_fr8205_info_reports_enospc_once(monkeypatch):
    filed: list[str] = []

    def _report(component, exc, *, site="", **_kw):
        filed.append(site)
        return {"ok": True}

    import runtime_failure

    monkeypatch.setattr(runtime_failure, "report", _report)
    monkeypatch.setattr(irc_agent, "_info_enospc_reported", False)
    monkeypatch.setattr(sys, "stdout", _EnospcStdout())
    irc_agent.info("one")
    irc_agent.info("two")
    assert filed == ["info-enospc"]


def test_fr8205_info_source_guards_oserror():
    src = (SCRIPTS / "irc_agent.py").read_text(encoding="utf-8")
    start = src.index("def info(msg: str)")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    assert "OSError" in body
    assert "ENOSPC" in body or "is_enospc" in body or "8205" in body
