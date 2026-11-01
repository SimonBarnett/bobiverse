"""FR #5678: leading id= that is not exactly 8 hex must not fall through to shell."""
from __future__ import annotations

import airc_console as ac
from airc_auth_helpers import ops_auth


def _core(**kw):
    auth = ops_auth("bob-marchhare", channel="#marchhare")
    return ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console", **kw
    )


def test_fr5678_leading_job_id_state_ok_none_bad():
    assert ac.leading_job_id_state("id=aabbccdd PRIORITY status") == (
        "ok",
        "aabbccdd",
        "PRIORITY status",
    )
    assert ac.leading_job_id_state("PRIORITY status") == ("none", None, "PRIORITY status")
    st, tok, rest = ac.leading_job_id_state("id=zz5588-nonhex PRIORITY status")
    assert st == "bad"
    assert tok == "zz5588-nonhex"
    assert rest.upper().startswith("PRIORITY")
    long_hex = "ab" * 150  # 300 hex chars
    st2, tok2, rest2 = ac.leading_job_id_state(f"id={long_hex} PRIORITY")
    assert st2 == "bad"
    assert tok2 == long_hex
    assert rest2.upper() == "PRIORITY"


def test_fr5678_long_hex_id_priority_is_bad_id_not_shell():
    calls: list = []

    def boom(*a, **k):
        calls.append((a, k))
        raise AssertionError("shell/priority must not run")

    core = _core(priority_runner=boom, shell_runner=None)
    # Attach a sentinel shell runner that records starts.
    class _NoShell:
        def start(self, nick, command):
            calls.append(("shell", nick, command))
            return nick

    core.shell_runner = _NoShell()
    long_hex = "ab" * 150
    hr = core.handle_raw(
        f":bob-marchhare!u@h PRIVMSG marchhare_console :id={long_hex} PRIORITY"
    )
    assert hr is not None
    assert hr.action == "bad_id"
    text = hr.reply or ""
    assert "code=bad_id" in text
    assert f"DONE id={long_hex} exit=2" in text
    assert "CommandNotFound" not in text
    assert calls == []


def test_fr5678_nonhex_id_network_is_bad_id_not_shell():
    calls: list = []

    class _NoShell:
        def start(self, nick, command):
            calls.append(("shell", command))
            return nick

    core = _core(shell_runner=_NoShell())
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console "
        ":id=zz5588-nonhex NETWORK diag"
    )
    assert hr and hr.action == "bad_id"
    text = hr.reply or ""
    assert "code=bad_id" in text
    assert "DONE id=zz5588-nonhex exit=2" in text
    assert calls == []


def test_fr5678_short_hex_id_update_is_bad_id():
    core = _core()
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=abc UPDATE airc"
    )
    assert hr and hr.action == "bad_id"
    assert "code=bad_id" in (hr.reply or "")
    assert "DONE id=abc exit=2" in (hr.reply or "")


def test_fr5678_valid_8hex_priority_still_routes():
    """Valid framing must keep working (regression vs bad_id gate)."""
    seen: list = []

    def runner(subcmd, instance_id, **kwargs):
        import airc_priority as ap

        jid = kwargs.get("job_id") or "11000001"
        seen.append((subcmd, instance_id, jid))
        return ap.PriorityVerbResult(
            ok=True,
            exit_code=0,
            job_id=jid,
            payload={"ok": True},
        )

    core = _core(priority_runner=runner)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console "
        ":id=11000001 PRIORITY status"
    )
    assert hr is not None
    assert hr.action == "priority"
    assert "code=bad_id" not in (hr.reply or "")
    assert seen and seen[0][0] == "status" and seen[0][2] == "11000001"


def test_fr5678_format_bad_id_reply_shape():
    text = ac.format_bad_id_reply("zz5588-nonhex")
    assert "code=bad_id" in text
    assert "DONE id=zz5588-nonhex exit=2" in text
    lines = text.splitlines()
    assert lines[0].startswith("err id=")
    assert lines[-1] == "DONE id=zz5588-nonhex exit=2"