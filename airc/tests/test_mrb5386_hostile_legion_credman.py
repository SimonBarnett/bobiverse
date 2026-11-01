"""MRB #5386 hostile pins for LEGION CredMan fail-closed (FR #5310)."""
from __future__ import annotations

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_mrb5386_target_and_fail_closed_before_install():
    assert lg.CREDMAN_TARGET == "PriorityAirc/LegionAdmin"
    ran = {"n": 0}

    def run_fn(spec):
        ran["n"] += 1
        return {"ok": True, "status": "ok"}

    body = lg.installer_legion_work(
        "box1", whatif=False, run_fn=run_fn, credman=lambda: {}
    )
    assert ran["n"] == 1
    assert body.get("credman_missing") is True
    assert body.get("identity") == "system"
    assert body["invoked_installer"] is True


def test_mrb5386_secret_not_on_wire():
    ident = {"username": "u", "password": "FAKE_hostile_pw"}
    body = lg.installer_legion_work(
        "box1",
        whatif=True,
        run_fn=lambda spec: {"ok": True, "status": "dry-run"},
        credman=lambda: ident,
    )
    assert "FAKE_hostile_pw" not in str(body)
    assert "password" not in body

    core = ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        legion_runner=lambda **kw: lg.run_legion_verb(
            credman=lambda: {}, wait=True, **kw
        ),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :LEGION box1")
    # FR #5659: missing CredMan falls through; no exit=126 fail-closed.
    assert "126" not in (hr.reply or "").split()
    assert "password=" not in (hr.reply or "").lower()
