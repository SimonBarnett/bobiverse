"""FR #5310: LEGION CredMan PriorityAirc/LegionAdmin; fail closed; redact."""
from __future__ import annotations

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5310_target_name_locked():
    assert lg.CREDMAN_TARGET == "PriorityAirc/LegionAdmin"


def test_fr5310_read_missing_fail_closed():
    def reader():
        raise lg.LegionCredmanError("credman-missing")

    try:
        lg.read_legion_credman(reader=reader)
        raise AssertionError("expected LegionCredmanError")
    except lg.LegionCredmanError as exc:
        assert "credman-missing" in str(exc)


def test_fr5310_installer_missing_does_not_invoke():
    def boom_run(spec):
        raise AssertionError("installer must not run")

    body = lg.installer_legion_work(
        "walrus",
        whatif=False,
        run_fn=boom_run,
        credman=lambda: {},
    )
    assert body["ok"] is False
    assert body["invoked_installer"] is False
    assert body["error"] == "credman-missing"
    assert "password" not in body


def test_fr5310_redacts_password_equals_and_secret():
    captured: list[dict] = []

    def run_fn(spec: dict) -> dict:
        captured.append(spec)
        return {"ok": True, "status": "dry-run"}

    ident = {"username": "wonderland\\legion", "password": "FAKE_" + "legion_pw"}
    body = lg.installer_legion_work(
        "walrus",
        whatif=True,
        run_fn=run_fn,
        credman=lambda: ident,
    )
    blob = str(body).lower() + str(captured).lower()
    assert "fake_legion_pw" not in blob
    assert "password=" not in blob
    assert "password" not in body
    assert captured[0]["username"] == "wonderland\\legion"
    assert captured[0]["password_via"] == "secure-env"
    assert captured[0]["credman_target"] == "PriorityAirc/LegionAdmin"


def test_fr5310_console_missing_exit_126():
    auth = ops_auth("op", channel="#tm")

    def runner(**kw):
        return lg.run_legion_verb(
            credman=lambda: {},
            wait=True,
            **kw,
        )

    core = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", legion_runner=runner
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION walrus")
    assert hr and hr.action == "legion"
    assert "126" in (hr.reply or "")
    assert "credman-missing" in (hr.reply or "")
    assert "password=" not in (hr.reply or "").lower()
    assert "FAKE_" not in (hr.reply or "")
