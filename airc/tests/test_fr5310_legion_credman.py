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


def test_fr5310_installer_missing_falls_to_system():
    """FR #5659: empty CredMan falls through to SYSTEM."""
    seen: list[dict] = []

    def run_fn(spec):
        seen.append(spec)
        return {"ok": True, "status": "ok"}

    body = lg.installer_legion_work(
        "walrus",
        whatif=False,
        run_fn=run_fn,
        credman=lambda: {},
    )
    assert body["ok"] is True
    assert body["invoked_installer"] is True
    assert body["identity"] == "system"
    assert body.get("credman_missing") is True
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
    assert captured[0]["password_via"] == "credman"
    assert captured[0]["credman_target"] == "PriorityAirc/LegionAdmin"


def test_fr5310_console_missing_falls_through_not_126():
    auth = ops_auth("op", channel="#tm")

    def runner(**kw):
        return lg.run_legion_verb(
            credman=lambda: {},
            wait=True,
            worker=lambda target, whatif=False, **k: {
                "ok": True,
                "status": "ok",
                "identity": "system",
                "identity_label": "system (HOST$)",
                "account": "HOST$",
                "credman_missing": True,
                "target": target,
            },
            **kw,
        )

    core = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", legion_runner=runner
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION walrus")
    assert hr and hr.action == "legion"
    assert "126" not in (hr.reply or "").split()
    assert "password=" not in (hr.reply or "").lower()
    assert "FAKE_" not in (hr.reply or "")
