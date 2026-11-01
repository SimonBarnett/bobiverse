"""FR #5825: console-side CRED persist via=irc sender (seal + send)."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_cred_irc as circ
import airc_cred_send as send
from airc_auth_helpers import ops_auth

FAKE_PW = "FAKE_" + "5825_cred_pw"
FAKE_USER = "Tabula"
QID = "c5825001"
TARGET = "PriorityWeb/hrs-priority-dev"


def _allowlist_path(tmp_path: Path) -> Path:
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


def _core(tmp_path: Path):
    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=None,
        priority_allowlist_path=str(_allowlist_path(tmp_path)),
    )
    core.irc_cred_sessions = circ.IrcCredSessionStore()
    return core


def test_fr5825_parse_hello_and_formatters():
    blob = (
        f"out id={QID} seq=1 CRED-HELLO token=aabbccddeeff0011 pub=abc "
        f"exp=9999999999 alg={circ.ALG} target={TARGET}\n"
        f"DONE id={QID} exit=0 cred-hello"
    )
    hello = send.parse_cred_hello(blob)
    assert hello is not None
    assert hello["token"] == "aabbccddeeff0011"
    assert hello["target"] == TARGET
    cmd = send.format_persist_command(qid=QID, target=TARGET)
    assert f"id={QID}" in cmd
    assert "via=irc" in cmd
    assert TARGET in cmd
    seals = send.format_seal_commands(qid=QID, token="aabb", chunks=["x", "y"])
    assert len(seals) == 2
    assert "seq=1/2" in seals[0] and "seq=2/2" in seals[1]


def test_fr5825_load_credman_and_pass_in():
    class Pair:
        username = FAKE_USER
        password = FAKE_PW

    got = send.load_credential(
        credman_source="PriorityWeb/local",
        reader=lambda _t: Pair(),
    )
    assert got["username"] == FAKE_USER
    assert got["password"] == FAKE_PW

    got2 = send.load_credential(username=FAKE_USER, password=FAKE_PW)
    assert got2["username"] == FAKE_USER

    try:
        send.load_credential(credman_source="missing", reader=lambda _t: None)
        assert False, "expected missing"
    except RuntimeError as exc:
        assert "credman-source-missing" in str(exc)


def test_fr5825_refuse_password_argv(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["airc_cred_send.py", "--password", "nope", "--machine", "x", "--target", "t", "--outbox", "o"],
    )
    rc = send.main(
        [
            "--machine",
            "tm",
            "--target",
            TARGET,
            "--outbox",
            "D:\\Temp\\no-such-outbox-5825.txt",
            "--password",
            "nope",
        ]
    )
    # argparse may error before our check when --password unknown; either 2
    assert rc != 0


def test_fr5825_send_e2e_against_console(tmp_path, monkeypatch):
    written: list[tuple[str, str, str]] = []

    def fake_write(tgt, user, pw):
        written.append((tgt, user, pw))
        return tgt

    import airc_passed_cred as pcred

    monkeypatch.setattr(pcred, "persist_credman", fake_write)
    core = _core(tmp_path)

    def transport(cmd: str) -> str:
        hr = core.handle_raw(f":op!u@h PRIVMSG tm_console :{cmd}")
        assert hr is not None
        return hr.reply or ""

    result = send.send_cred_via_irc(
        target=TARGET,
        username=FAKE_USER,
        password=FAKE_PW,
        transport=transport,
        qid=QID,
    )
    assert result["ok"] is True
    assert result["code"] == "cred-persisted"
    assert result["account"] == FAKE_USER
    assert FAKE_PW not in json.dumps(result)
    assert written == [(TARGET, FAKE_USER, FAKE_PW)]


def test_fr5825_send_allowlist_reject(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "airc_passed_cred.persist_credman", lambda *a, **k: TARGET
    )
    core = _core(tmp_path)

    def transport(cmd: str) -> str:
        hr = core.handle_raw(f":op!u@h PRIVMSG tm_console :{cmd}")
        return hr.reply or ""

    result = send.send_cred_via_irc(
        target="PriorityWeb/not-listed",
        username=FAKE_USER,
        password=FAKE_PW,
        transport=transport,
        qid=QID,
    )
    assert result["ok"] is False
    assert result["code"] == "cred-target-not-allowlisted"
    assert FAKE_PW not in result["code"]


def test_fr5825_secret_absent_from_transport_log(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "airc_passed_cred.persist_credman", lambda *a, **k: TARGET
    )
    core = _core(tmp_path)
    seen: list[str] = []

    def transport(cmd: str) -> str:
        # operator must not put plaintext password in the command
        assert FAKE_PW not in cmd
        hr = core.handle_raw(f":op!u@h PRIVMSG tm_console :{cmd}")
        reply = hr.reply or ""
        seen.append(reply)
        assert FAKE_PW not in reply
        return reply

    result = send.send_cred_via_irc(
        target=TARGET,
        username=FAKE_USER,
        password=FAKE_PW,
        transport=transport,
        qid=QID,
    )
    assert result["ok"] is True
    assert FAKE_PW not in "\n".join(seen)


def test_fr5825_expired_hello_window(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "airc_passed_cred.persist_credman", lambda *a, **k: TARGET
    )
    core = _core(tmp_path)
    calls = {"n": 0}

    def transport(cmd: str) -> str:
        calls["n"] += 1
        hr = core.handle_raw(f":op!u@h PRIVMSG tm_console :{cmd}")
        return hr.reply or ""

    # Force clock past exp immediately after HELLO parse.
    result = send.send_cred_via_irc(
        target=TARGET,
        username=FAKE_USER,
        password=FAKE_PW,
        transport=transport,
        qid=QID,
        now=lambda: 10**12,
    )
    assert result["ok"] is False
    assert result["code"] == "cred-expired"


def test_fr5825_skill_and_script_pins():
    root = Path(__file__).resolve().parents[2]
    cmd = (root / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    tro = (
        root / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "Send-AircCred" in cmd or "airc_cred_send" in cmd
    assert "FR #5825" in cmd
    assert "FR #5825" in tro
    assert (root / "airc/scripts/airc_cred_send.py").is_file()
    assert (root / "airc/scripts/Send-AircCred.ps1").is_file()
    assert "\u2014" not in cmd
