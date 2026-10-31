"""FR #5352: NICKNAME_RESERVED is a credential stall, not a bob-ear crash."""
from __future__ import annotations

from repo_layout import ROOT

IRC = ROOT / "common" / "scripts" / "irc_agent.py"


def _surface_fn() -> str:
    t = IRC.read_text(encoding="utf-8")
    i = t.index("def _surface_nickname_reserved")
    return t[i : i + 900]


def test_fr5352_surface_does_not_crash_report():
    chunk = _surface_fn()
    assert "#5352" in chunk
    assert "import crash_report" not in chunk
    assert "report_exception" not in chunk


def test_fr5352_run_forever_backs_off_reserved_nick():
    t = IRC.read_text(encoding="utf-8")
    i = t.index("def run_forever")
    chunk = t[i : i + 1800]
    assert "NICKNAME_RESERVED" in chunk
    assert "_surface_nickname_reserved" in chunk
    assert "NICKNAME_RESERVED_BACKOFF" in chunk or "300" in chunk
