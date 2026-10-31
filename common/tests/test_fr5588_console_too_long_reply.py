"""FR #5588: rejected over-long *_console PRIVMSG must emit synthetic err+DONE."""
from __future__ import annotations

import json
from pathlib import Path

import inbound_transcript
import irc_agent as agent


def test_fr5588_note_helper_writes_err_and_done(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    body = "id=deadbeef cmd: " + ("x" * 500)
    agent.note_overlong_console_privmsg_reject(
        home,
        console_nick="marchhare_console",
        ear_nick="Bob-marchhare",
        text=body,
        budget=400,
    )
    rows_path = home / "airc-replies.jsonl"
    assert rows_path.is_file()
    rows = [json.loads(x) for x in rows_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 2
    assert rows[0]["from"] == "marchhare_console"
    assert rows[0]["body"].startswith("err id=deadbeef seq=1 code=too_long")
    assert "bytes=" in rows[0]["body"]
    assert "budget=400" in rows[0]["body"]
    assert rows[1]["body"] == "DONE id=deadbeef exit=1"
    transcript = (home / "inbound-transcript.log").read_text(encoding="utf-8")
    assert "err id=deadbeef seq=1 code=too_long" in transcript
    assert "DONE id=deadbeef exit=1" in transcript
    assert "marchhare_console" in transcript


def test_fr5588_expand_with_home_notes_reject(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    body = "id=aabbccdd cmd: " + ("y" * 200)
    line = f"PRIVMSG marchhare_console :{body}"
    out = agent.expand_irc_outbound_line(
        line,
        nick="Bob-marchhare",
        text_max=80,
        home=home,
        ear_nick="Bob-marchhare",
    )
    assert out == []
    rows = [
        json.loads(x)
        for x in (home / "airc-replies.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    assert rows[0]["body"].startswith("err id=aabbccdd seq=1 code=too_long")
    assert rows[1]["body"] == "DONE id=aabbccdd exit=1"


def test_fr5588_reject_without_id_still_drops_wire_only(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    body = "cmd: " + ("z" * 200)
    out = agent.expand_irc_outbound_line(
        f"PRIVMSG marchhare_console :{body}",
        nick="Bob-marchhare",
        text_max=80,
        home=home,
        ear_nick="Bob-marchhare",
    )
    assert out == []
    assert not (home / "airc-replies.jsonl").exists()


def test_fr5588_short_console_does_not_write_synthetic(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    out = agent.expand_irc_outbound_line(
        "PRIVMSG marchhare_console :id=deadbeef STATUS",
        nick="Bob-marchhare",
        text_max=80,
        home=home,
        ear_nick="Bob-marchhare",
    )
    assert out == ["PRIVMSG marchhare_console :id=deadbeef STATUS"]
    assert not (home / "airc-replies.jsonl").exists()


def test_fr5588_note_helper_noop_without_home():
    agent.note_overlong_console_privmsg_reject(
        None,
        console_nick="marchhare_console",
        ear_nick="Bob-marchhare",
        text="id=deadbeef cmd: " + ("x" * 500),
        budget=400,
    )
