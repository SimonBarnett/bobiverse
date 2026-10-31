"""FR #5615: EXTENSION action and -WhatIf are whole tokens; else usage error."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_extension as ex
from airc_auth_helpers import ops_auth


def test_fr5615_prefix_actions_are_usage_not_install():
    for text in (
        "EXTENSION installation",
        "EXTENSION install-now",
        "EXTENSION statusXYZ",
        "EXTENSION installer -WhatIf",
    ):
        p = ex.parse_extension_command(text)
        assert p is not None
        assert p.get("error")
        assert p.get("action") not in ("install", "status") or p.get("error")


def test_fr5615_whatif_is_whole_token_only():
    p = ex.parse_extension_command("EXTENSION installer -whatiffy")
    assert p is not None and p.get("error")
    assert p.get("whatif") is not True
    ok = ex.parse_extension_command("EXTENSION install -WhatIf")
    assert ok is not None and not ok.get("error")
    assert ok["action"] == "install" and ok["whatif"] is True
    bogus = ex.parse_extension_command("EXTENSION status -WhatIf -Bogus")
    assert bogus is not None and bogus.get("error")


def test_fr5615_console_installation_does_not_run(monkeypatch):
    called = {"n": 0}

    def boom(**_kw):
        called["n"] += 1
        raise AssertionError("must not run GPO install")

    core = ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        extension_runner=boom,
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd EXTENSION installation")
    assert called["n"] == 0
    assert hr is not None
    assert "126" in (hr.reply or "")
    assert "bad-extension-cmd" in (hr.reply or "")


def test_fr5615_pins():
    src = Path(ex.__file__).read_text(encoding="utf-8")
    assert "FR #5615" in src
    assert r"(?=\s|$)" in src or "split()" in src
    assert not Path(ex.__file__).read_bytes().startswith(b"\xef\xbb\xbf")
