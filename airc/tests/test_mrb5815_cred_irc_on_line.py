"""MRB #5815 fix: CRED via=irc HELLO/SEAL must reach IRC via on_line (action=cred)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import airc_console as ac
import airc_console_service as svc
import airc_cred_irc as circ
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FAKE_PW = "FAKE_" + "5815_cred_pw"
FAKE_USER = "Tabula"
QID = "c5815001"
TARGET = "PriorityWeb/hrs-priority-dev"
SVC = ROOT / "airc" / "scripts" / "airc_console_service.py"


def _allow(tmp_path: Path) -> Path:
    p = tmp_path / "priority-instances.json"
    p.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "hrs-dev",
                        "url": "https://priority.example.invalid",
                        "company": "live1",
                        "user": FAKE_USER,
                        "credentialTarget": TARGET,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return p


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(["--machine", "tm", "--home", str(tmp_path)])
    service = svc.AircConsoleService(args)
    sent: list[tuple[str, str]] = []
    logs: list[str] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append((nick, text))
    monkeypatch.setattr(svc, "info", lambda msg: logs.append(str(msg)))
    auth = ops_auth("op", channel="#tm")
    service.core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=None,
        priority_allowlist_path=str(_allow(tmp_path)),
    )
    return service, sent, logs


def test_mrb5815_service_source_dispatches_cred():
    text = SVC.read_text(encoding="utf-8")
    assert '"cred"' in text or "'cred'" in text
    assert "FR #5811" in text or "MRB #5815" in text or "5815" in text


def test_mrb5815_cred_hello_reaches_irc(tmp_path, monkeypatch):
    service, sent, logs = _service(tmp_path, monkeypatch)
    service.on_line(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    bodies = [t for _, t in sent]
    assert any("CRED-HELLO" in t for t in bodies), bodies
    assert any(t.startswith(f"DONE id={QID} exit=0") and "cred-hello" in t for t in bodies), bodies
    assert FAKE_PW not in "\n".join(bodies)
    assert any("cred-reply" in m or "action=cred" in m for m in logs)


def test_mrb5815_cred_seal_persisted_reaches_irc(tmp_path, monkeypatch):
    written: list[tuple[str, str, str]] = []

    def fake_write(tgt, user, pw):
        written.append((tgt, user, pw))
        return tgt

    monkeypatch.setattr(pcred, "persist_credman", fake_write)
    service, sent, _logs = _service(tmp_path, monkeypatch)
    service.on_line(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    hello_blob = "\n".join(t for _, t in sent)
    m = re.search(
        r"CRED-HELLO token=(\S+) pub=(\S+) exp=(\d+) alg=(\S+) target=(\S+)",
        hello_blob,
    )
    assert m, hello_blob
    token, pub, exp = m.group(1), m.group(2), int(m.group(3))
    chunks = circ.seal_cred_payload(
        pub_b64=pub,
        token=token,
        target=TARGET,
        exp=exp,
        username=FAKE_USER,
        password=FAKE_PW,
    )
    sent.clear()
    for i, ct in enumerate(chunks, start=1):
        service.on_line(
            f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
            f"token={token} seq={i}/{len(chunks)} ct={ct}"
        )
    bodies = [t for _, t in sent]
    assert any("cred-persisted" in t for t in bodies), bodies
    assert any(f"target={TARGET}" in t for t in bodies), bodies
    assert FAKE_PW not in "\n".join(bodies)
    assert written == [(TARGET, FAKE_USER, FAKE_PW)]


def test_mrb5815_core_binds_irc_cred_sessions():
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console")
    assert getattr(core, "irc_cred_sessions", None) is not None
