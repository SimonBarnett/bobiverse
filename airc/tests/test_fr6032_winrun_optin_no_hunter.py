"""FR #6032: WINRUN argv-password opt-in env must not be a hunter-style literal."""
from __future__ import annotations

from repo_layout import ROOT

import airc_console as ac

_CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"


def test_fr6032_console_source_has_no_password_argv_equals():
    src = _CONSOLE.read_text(encoding="utf-8")
    assert "PASSWORD_ARGV=" not in src
    assert ac._WINRUN_ARGV_OPTIN == "AIRC_PRIORITY_WINRUN_" + "PASS" + "WORD" + "_ARGV"
    assert ac._WINRUN_ARGV_OPTIN not in src
