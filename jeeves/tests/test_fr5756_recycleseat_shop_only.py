"""FR #5756: !recycleseat goes to shop only; never #bobiverse."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines

from test_fr5163_mrb_reviewer_deadlock import _mrb_row


def _outbox_text(tmp_path: Path) -> str:
    outbox = tmp_path / "chair-outbox.txt"
    if not outbox.is_file():
        outbox = Path(bobreport.fleet_digest_home(tmp_path)) / "chair-outbox.txt"
    return outbox.read_text(encoding="utf-8") if outbox.is_file() else ""


def test_fr5756_bored_latency_shop_only_never_bobiverse(tmp_path, monkeypatch):
    nick = "flamingo-64124"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 1_700_000.0
    lines = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        last_activity={},
        accepted=[],
        now=now,
        install_root=install,
    )
    assert any("bored-latency recycleseat=flamingo-64124" in x for x in lines), lines
    text = _outbox_text(tmp_path)
    assert "PRIVMSG #flamingo :!recycleseat flamingo-64124 flamingo" in text, text
    assert "PRIVMSG #bobiverse :" not in text
    assert text.count("!recycleseat") == 1


def test_fr5756_mrb_deadlock_shop_only_never_bobiverse(tmp_path, monkeypatch):
    nick = "flamingo-48304"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(
                    repo="SimonBarnett/agentic_fomprep",
                    num=241,
                    author=nick,
                )
            ],
            "accepted": [],
            "done": [],
        },
    )
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=1_700_000.0
    )
    assert any("recycleseat=flamingo-48304" in x for x in lines), lines
    text = _outbox_text(tmp_path)
    assert "PRIVMSG #flamingo :!recycleseat flamingo-48304 flamingo" in text, text
    assert "PRIVMSG #bobiverse :" not in text


def test_fr5756_no_machine_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # Seat nick that does not parse to a machine id.
    nick = "orphan-seat"
    install = tmp_path / "install"
    install.mkdir()
    monkeypatch.setattr(
        gitclaim,
        "free_seat_nicks",
        lambda home: {nick},
    )
    monkeypatch.setattr(
        "stall_detectors.detect_bored_latency",
        lambda snap: [
            {
                "id": "bored-latency",
                "key": nick,
                "evidence": {"nick": nick, "lag_s": 999},
            }
        ],
    )
    monkeypatch.setattr(bobreport, "parse_seat_nick", lambda n: None)
    lines = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: 1.0},
        now=1_700_000.0,
        install_root=install,
    )
    assert any("recycle_skipped:no_machine" in x for x in lines), lines
    text = _outbox_text(tmp_path)
    assert "!recycleseat" not in text


def test_fr5756_shared_cooldown_across_heal_paths(tmp_path, monkeypatch):
    nick = "flamingo-64124"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 1_700_000.0
    first = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now,
        install_root=install,
    )
    assert first
    # MRB deadlock heal must honour the same per-nick cooldown.
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(
                    repo="SimonBarnett/agentic_fomprep",
                    num=99,
                    author=nick,
                )
            ],
            "accepted": [],
            "done": [],
        },
    )
    second = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=now + 60
    )
    assert not any("recycleseat=" in x for x in second), second
