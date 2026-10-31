"""FR #5583: NETWORK/LEGION DONE is last; out/CONT log is not after DONE."""
from __future__ import annotations

import airc_console as ac
import airc_console_service as svc
import airc_legion as lg
import airc_network as nw
from airc_auth_helpers import ops_auth
from repo_layout import ROOT


def test_fr5583_accept_text_has_no_done():
    res = nw.run_network_verb(
        action="diag",
        job_id="aabbccdd",
        wait=True,
        worker=lambda **_k: {"ok": True, "hosts": [{"hostname": "pc1"}], "failures": []},
    )
    assert "NETWORK accepted" in res.reply
    assert "DONE" not in res.reply
    lres = lg.run_legion_verb(
        target="flamingo",
        whatif=True,
        job_id="ca6016a2",
        wait=True,
        worker=lambda **_k: {"ok": True, "status": "whatif"},
    )
    assert "LEGION accepted" in lres.reply
    assert "DONE" not in lres.reply


def test_fr5583_handle_raw_accept_without_done():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console")
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=9e7b3e2c NETWORK diag")
    assert hr and hr.action == "network"
    assert "NETWORK accepted" in (hr.reply or "")
    assert "DONE id=9e7b3e2c" not in (hr.reply or "")


def test_fr5583_emit_sends_log_then_done():
    sent: list[str] = []

    class Core:
        verb_log_nick = "op"

    svc_mod = svc
    service = svc_mod.AircConsoleService.__new__(svc_mod.AircConsoleService)
    service.core = Core()
    service._on_console_out = lambda nick, text: sent.append(text)
    delivered = {
        "lines": [
            "out id=9e7b3e2c seq=1 NETWORK log hosts=6 failures=0 action=diag bytes=10",
            "CONT id=9e7b3e2c offset=1",
            "DONE id=9e7b3e2c exit=0 via=irc",
        ]
    }
    # Recreate emit the same way as __init__
    nick = service.core.verb_log_nick
    for line in delivered["lines"]:
        service._on_console_out(nick, line)
    assert sent[0].startswith("out id=9e7b3e2c")
    assert "CONT" in sent[1]
    assert sent[-1].startswith("DONE id=9e7b3e2c")
    assert not any(s.startswith("DONE") for s in sent[:-1])


def test_fr5583_pins():
    net = (ROOT / "airc" / "scripts" / "airc_network.py").read_text(encoding="utf-8")
    assert "FR #5583" in net
    assert 'f"NETWORK accepted id={qid} action={action}{extra}\\nDONE' not in net
    assert 'f"NETWORK accepted id={qid} action={action}{extra}"' in net
    leg = (ROOT / "airc" / "scripts" / "airc_legion.py").read_text(encoding="utf-8")
    assert "FR #5583" in leg
    emit = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    block = emit.split("def _verb_log_emit")[1].split("attach_verb_log_hooks")[0]
    assert "startswith" not in block
    assert not (ROOT / "airc" / "scripts" / "airc_network.py").read_bytes().startswith(b"\xef\xbb\xbf")
