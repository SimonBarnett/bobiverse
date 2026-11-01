"""FR #5812: CRED persist via=irc (E2E sealed over existing TLS IRC hop)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import airc_console as ac
import airc_cred_irc as circ
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth

FAKE_PW = "FAKE_" + "5812_cred_pw"
FAKE_USER = "Tabula"
QID = "c5812001"
TARGET = "PriorityWeb/hrs-priority-dev"
OTHER = "PriorityWeb/not-listed"


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


def _core(tmp_path: Path | None = None):
    auth = ops_auth("op", channel="#tm")
    kwargs = {
        "machine": "tm",
        "auth": auth,
        "nick": "tm_console",
        "shell_runner": None,
    }
    if tmp_path is not None:
        kwargs["priority_allowlist_path"] = str(_allowlist_path(tmp_path))
    core = ac.AircConsoleCore(**kwargs)
    core.irc_cred_sessions = circ.IrcCredSessionStore()
    return core


def _hello_fields(reply: str) -> dict[str, str]:
    m = re.search(
        r"CRED-HELLO token=(\S+) pub=(\S+) exp=(\d+) alg=(\S+) target=(\S+)",
        reply or "",
    )
    assert m, reply
    return {
        "token": m.group(1),
        "pub": m.group(2),
        "exp": m.group(3),
        "alg": m.group(4),
        "target": m.group(5),
    }


def test_fr5812_parse_persist_irc():
    parsed = pcred.parse_cred_command(
        f"id={QID} CRED persist target={TARGET} via=irc"
    )
    assert parsed is not None
    assert parsed["qid"] == QID
    assert parsed["persist"] is True
    assert parsed["via"] == "irc"
    assert parsed["target"] == TARGET


def test_fr5812_parse_cred_seal():
    parsed = circ.parse_cred_seal_command(
        f"id={QID} CRED-SEAL token=aabbccddeeff0011 seq=1/1 ct=abc"
    )
    assert parsed is not None
    assert parsed["qid"] == QID
    assert parsed["token"] == "aabbccddeeff0011"
    assert parsed["seq"] == "1/1"
    assert parsed["ct"] == "abc"


def test_fr5812_seal_roundtrip_unit():
    store = circ.IrcCredSessionStore()
    hello = circ.start_irc_persist_session(
        target=TARGET, nick="op", qid=QID, store=store
    )
    chunks = circ.seal_cred_payload(
        pub_b64=hello["pub"],
        token=hello["token"],
        target=TARGET,
        exp=hello["exp"],
        username=FAKE_USER,
        password=FAKE_PW,
    )
    assert len(chunks) >= 1
    written: list[tuple[str, str, str]] = []

    def fake_write(tgt, user, pw):
        written.append((tgt, user, pw))
        return tgt

    result = None
    for i, ct in enumerate(chunks, start=1):
        result = circ.ingest_seal_chunk(
            nick="op",
            token=hello["token"],
            seq=f"{i}/{len(chunks)}",
            ct_b64=ct,
            store=store,
            allowlisted={TARGET},
            writer=fake_write,
        )
    assert result is not None
    assert result["ok"] is True
    assert result["code"] == "cred-persisted"
    assert written == [(TARGET, FAKE_USER, FAKE_PW)]


def test_fr5812_persist_irc_e2e_console(tmp_path, monkeypatch):
    written: list[tuple[str, str, str]] = []

    def fake_write(tgt, user, pw):
        written.append((tgt, user, pw))
        return tgt

    monkeypatch.setattr(pcred, "persist_credman", fake_write)
    core = _core(tmp_path)
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    assert hr is not None
    assert hr.action == "cred"
    text = hr.reply or ""
    assert "CRED-HELLO" in text
    assert FAKE_PW not in text
    assert "password=" not in text.lower()
    fields = _hello_fields(text)
    assert fields["target"] == TARGET
    assert fields["alg"] == circ.ALG

    chunks = circ.seal_cred_payload(
        pub_b64=fields["pub"],
        token=fields["token"],
        target=TARGET,
        exp=int(fields["exp"]),
        username=FAKE_USER,
        password=FAKE_PW,
    )
    last = None
    for i, ct in enumerate(chunks, start=1):
        last = core.handle_raw(
            f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
            f"token={fields['token']} seq={i}/{len(chunks)} ct={ct}"
        )
    assert last is not None
    reply = last.reply or ""
    assert "cred-persisted" in reply
    assert f"target={TARGET}" in reply
    assert f"account={FAKE_USER}" in reply
    assert FAKE_PW not in reply
    assert written == [(TARGET, FAKE_USER, FAKE_PW)]


def test_fr5812_wrong_sender_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(pcred, "persist_credman", lambda *a, **k: TARGET)
    core = _core(tmp_path)
    # Second auth'd nick so console auth allows the line; session nick bind rejects.
    core.auth = ops_auth("op", "eve", channel="#tm")
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    fields = _hello_fields(hr.reply or "")
    chunks = circ.seal_cred_payload(
        pub_b64=fields["pub"],
        token=fields["token"],
        target=TARGET,
        exp=int(fields["exp"]),
        username=FAKE_USER,
        password=FAKE_PW,
    )
    bad = core.handle_raw(
        f":eve!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
        f"token={fields['token']} seq=1/{len(chunks)} ct={chunks[0]}"
    )
    assert bad is not None
    assert "cred-rejected-auth" in (bad.reply or "")
    assert FAKE_PW not in (bad.reply or "")


def test_fr5812_replay_rejected(tmp_path, monkeypatch):
    written: list = []

    def fake_write(tgt, user, pw):
        written.append((tgt, user, pw))
        return tgt

    monkeypatch.setattr(pcred, "persist_credman", fake_write)
    core = _core(tmp_path)
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    fields = _hello_fields(hr.reply or "")
    chunks = circ.seal_cred_payload(
        pub_b64=fields["pub"],
        token=fields["token"],
        target=TARGET,
        exp=int(fields["exp"]),
        username=FAKE_USER,
        password=FAKE_PW,
    )
    assert len(chunks) == 1
    ok = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
        f"token={fields['token']} seq=1/1 ct={chunks[0]}"
    )
    assert "cred-persisted" in (ok.reply or "")
    replay = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
        f"token={fields['token']} seq=1/1 ct={chunks[0]}"
    )
    assert "cred-replay" in (replay.reply or "") or "cred-expired" in (
        replay.reply or ""
    )
    assert len(written) == 1


def test_fr5812_expired_token(tmp_path, monkeypatch):
    monkeypatch.setattr(pcred, "persist_credman", lambda *a, **k: TARGET)
    core = _core(tmp_path)
    store = core.irc_cred_sessions
    hello = circ.start_irc_persist_session(
        target=TARGET,
        nick="op",
        qid=QID,
        ttl_s=0.01,
        store=store,
    )
    time.sleep(0.05)
    chunks = circ.seal_cred_payload(
        pub_b64=hello["pub"],
        token=hello["token"],
        target=TARGET,
        exp=hello["exp"],
        username=FAKE_USER,
        password=FAKE_PW,
    )
    result = circ.ingest_seal_chunk(
        nick="op",
        token=hello["token"],
        seq="1/1",
        ct_b64=chunks[0],
        store=store,
        allowlisted={TARGET},
        writer=lambda *a, **k: TARGET,
        now_unix=time.time() + 120,
    )
    assert result["ok"] is False
    assert result["code"] == "cred-expired"


def test_fr5812_target_not_allowlisted(tmp_path):
    core = _core(tmp_path)
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={OTHER} via=irc"
    )
    assert hr is not None
    assert "cred-target-not-allowlisted" in (hr.reply or "")


def test_fr5812_bad_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(pcred, "persist_credman", lambda *a, **k: TARGET)
    core = _core(tmp_path)
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    fields = _hello_fields(hr.reply or "")
    bad = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
        f"token={fields['token']} seq=1/1 ct=not-valid-ciphertext!!!"
    )
    assert bad is not None
    assert "cred-bad-payload" in (bad.reply or "")
    assert FAKE_PW not in (bad.reply or "")


def test_fr5812_secret_absent_from_replies(tmp_path, monkeypatch):
    monkeypatch.setattr(pcred, "persist_credman", lambda *a, **k: TARGET)
    core = _core(tmp_path)
    blobs: list[str] = []
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=irc"
    )
    blobs.append(hr.reply or "")
    fields = _hello_fields(hr.reply or "")
    chunks = circ.seal_cred_payload(
        pub_b64=fields["pub"],
        token=fields["token"],
        target=TARGET,
        exp=int(fields["exp"]),
        username=FAKE_USER,
        password=FAKE_PW,
    )
    for i, ct in enumerate(chunks, start=1):
        r = core.handle_raw(
            f":op!u@h PRIVMSG tm_console :id={QID} CRED-SEAL "
            f"token={fields['token']} seq={i}/{len(chunks)} ct={ct}"
        )
        blobs.append(r.reply or "")
    joined = "\n".join(blobs)
    assert FAKE_PW not in joined
    assert "password=" not in joined.lower()
    # ciphertext may appear in operator CRED-SEAL command text (input), not replies
    for blob in blobs:
        assert FAKE_PW not in blob


def test_fr5812_skill_and_docs_pins():
    root = Path(__file__).resolve().parents[2]
    cmd = (root / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(
        encoding="utf-8"
    )
    tro = (
        root / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
    ).read_text(encoding="utf-8")
    docs = (root / "airc/docs/airc-remote-control.md").read_text(encoding="utf-8")
    assert "via=irc" in cmd
    assert "CRED-HELLO" in cmd
    assert "CRED-SEAL" in cmd
    assert "FR #5812" in cmd
    assert "FR #5812" in tro
    assert "cred-rejected-auth" in tro or "via=irc" in tro
    assert "via=irc" in docs
    assert "FR #5812" in docs
    assert "\u2014" not in cmd  # ASCII --- only (FR #3935)
