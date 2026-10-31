"""FR #5519: IRC CONT after NETWORK/EXTENSION/LEGION must have a resume buffer."""
from __future__ import annotations

import json
import threading
import time

import airc_console as ac
import airc_network as nw
from airc_auth_helpers import ops_auth


def _core(**kw):
    rec: list[tuple[str, str]] = []

    def on_reply(nick: str, line: str) -> None:
        rec.append((nick, line))

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=on_reply, wait=True),
        **kw,
    )
    return core, rec


def test_fr5519_network_cont_returns_payload_without_dcclisten():
    done = threading.Event()

    def runner(**kw):
        on_done = kw.get("on_done")
        qid = kw.get("job_id") or "aabbccdd"
        res = nw.NetworkVerbResult(
            True,
            f"NETWORK accepted id={qid}",
            job_id=qid,
            hosts=[{"hostname": "pc1", "ips": ["10.0.0.1"], "ou": "OU=PCs"}],
            failures=[],
        )
        if on_done:
            on_done(res)
            done.set()
        return res

    core, rec = _core(network_runner=runner)
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK diag")
    assert hr and hr.action == "network"
    assert done.wait(2.0)
    # Live path: CONT must not be unknown.
    hr2 = core.handle_raw(":op!u@h PRIVMSG tm_console :CONT id=aabbccdd")
    assert hr2 and hr2.action == "shell_cont"
    joined = "\n".join(ln for _n, ln in rec)
    assert "no resume buffer" not in joined
    assert "DONE id=aabbccdd exit=1" not in joined
    outs = [ln for _n, ln in rec if ln.startswith("out id=aabbccdd")]
    blob = "".join(ln.split(" ", 4)[-1] for ln in outs if "NETWORK log" not in ln)
    # Dummy first line + JSON chunks, or JSON-only pages.
    body = blob if blob.startswith("{") else blob[blob.find("{") :] if "{" in blob else blob
    if not body.startswith("{"):
        body = "".join(ln.split(" ", 4)[-1] for ln in outs)
        if "log" in body[:8] and "{" in body:
            body = body[body.index("{") :]
    data = json.loads(body)
    assert data["hosts"][0]["hostname"] == "pc1"


def test_fr5519_cont_isolation_other_nick():
    def runner(**kw):
        on_done = kw.get("on_done")
        qid = kw.get("job_id") or "aabbccdd"
        res = nw.NetworkVerbResult(True, "NETWORK accepted", job_id=qid, hosts=[], failures=[])
        if on_done:
            on_done(res)
        return res

    core, rec = _core(network_runner=runner)
    core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK diag")
    time.sleep(0.05)
    rec.clear()
    assert core.shell_runner is not None
    core.shell_runner.continue_replies("other", "aabbccdd")
    joined = "\n".join(ln for _n, ln in rec)
    assert "no resume buffer" in joined


def test_fr5519_dcc_fail_includes_cont_and_payload_bytes():
    out = nw.deliver_network_payload(
        job_id="deadbeef",
        payload=nw.build_network_payload("diag", hosts=[], failures=[]),
        offer=object(),
        send_fn=lambda *_a, **_k: (_ for _ in ()).throw(OSError("refused")),
    )
    assert out["via"] == "irc"
    assert any("CONT id=deadbeef" in x for x in out["lines"])
    assert out.get("payload")
