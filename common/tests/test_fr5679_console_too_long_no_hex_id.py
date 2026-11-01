"""FR #5679: over-long *_console reject must still emit synthetic err+DONE without hex id."""
from __future__ import annotations

import json
from pathlib import Path

import irc_agent as agent


def _rows(home: Path) -> list[dict]:
    path = home / "airc-replies.jsonl"
    assert path.is_file(), "expected airc-replies.jsonl for visible reject"
    return [
        json.loads(x)
        for x in path.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]


def test_fr5679_reject_without_id_writes_synthetic(tmp_path: Path):
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
    rows = _rows(home)
    assert len(rows) == 2
    assert rows[0]["from"] == "marchhare_console"
    assert rows[0]["body"].startswith("err seq=1 code=too_long")
    assert "bytes=" in rows[0]["body"]
    assert "budget=80" in rows[0]["body"]
    assert " id=" not in rows[0]["body"]
    assert rows[1]["body"] == "DONE exit=1"
    transcript = (home / "inbound-transcript.log").read_text(encoding="utf-8")
    assert "err seq=1 code=too_long" in transcript
    assert "DONE exit=1" in transcript


def test_fr5679_nonhex_id_still_writes_synthetic(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    body = "id=zz5588-nonhex Write-Output '" + ("x" * 560) + "'"
    agent.note_overlong_console_privmsg_reject(
        home,
        console_nick="marchhare_console",
        ear_nick="Bob-marchhare",
        text=body,
        budget=400,
    )
    rows = _rows(home)
    assert len(rows) == 2
    err = rows[0]["body"]
    assert err.startswith("err seq=1 code=too_long")
    assert "id=zz5588-nonhex" in err
    assert "bytes=" in err and "budget=400" in err
    assert rows[1]["body"] == "DONE exit=1"
    # Must not pretend a hex corr id for Invoke-AircRemote waiters that key on hex.
    assert "id=zz5588" not in rows[1]["body"]


def test_mrb5680_expand_nonhex_id_writes_visible_reject(tmp_path: Path):
    """Hostile MRB #5680: expand_irc_outbound_line path for non-hex id= (issue repro)."""
    home = tmp_path / "home"
    home.mkdir()
    body = "id=zz5588-nonhex Write-Output '" + ("x" * 560) + "'"
    out = agent.expand_irc_outbound_line(
        f"PRIVMSG marchhare_console :{body}",
        nick="Bob-marchhare",
        text_max=400,
        home=home,
        ear_nick="Bob-marchhare",
    )
    assert out == []
    rows = _rows(home)
    assert len(rows) == 2
    assert "id=zz5588-nonhex" in rows[0]["body"]
    assert rows[0]["body"].startswith("err seq=1 code=too_long")
    assert rows[1]["body"] == "DONE exit=1"
    assert "DONE id=" not in rows[1]["body"]


def test_fr5679_is_airc_console_reply_accepts_idless_err_seq():
    assert agent.is_airc_console_reply(
        "marchhare_console", "err seq=1 code=too_long bytes=592 budget=400"
    )
    assert agent.is_airc_console_reply(
        "marchhare_console",
        "err seq=1 code=too_long id=zz5588-nonhex bytes=592 budget=400",
    )
    assert agent.is_airc_console_reply("marchhare_console", "DONE exit=1")
    # out without id still rejected (not a synthetic too_long shape).
    assert not agent.is_airc_console_reply(
        "marchhare_console", "out seq=1 code=too_long bytes=1 budget=1"
    )


def test_fr5679_hex_id_path_unchanged(tmp_path: Path):
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
    rows = _rows(home)
    assert rows[0]["body"].startswith("err id=deadbeef seq=1 code=too_long")
    assert rows[1]["body"] == "DONE id=deadbeef exit=1"
