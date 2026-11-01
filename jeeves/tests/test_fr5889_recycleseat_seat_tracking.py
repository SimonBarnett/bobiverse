"""FR #5889: per-seat recycleseat tracking; author-only flags (no recycle storm)."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import recycleseat

from test_fr5163_mrb_reviewer_deadlock import _mrb_row, _two_idle


def _outbox_text(tmp_path: Path) -> str:
    outbox = tmp_path / "chair-outbox.txt"
    if not outbox.is_file():
        outbox = Path(bobreport.fleet_digest_home(tmp_path)) / "chair-outbox.txt"
    return outbox.read_text(encoding="utf-8") if outbox.is_file() else ""


def test_fr5889_author_only_flags_without_recycle(tmp_path, monkeypatch):
    a, b = _two_idle(tmp_path, monkeypatch)
    both = f"{a},{b}"
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(
                    repo="SimonBarnett/bobiverse",
                    num=1001,
                    author=a,
                    **{"author_seats": both},
                ),
                _mrb_row(
                    repo="SimonBarnett/bobiverse",
                    num=1002,
                    author=b,
                    **{"author_seats": both},
                ),
            ],
            "accepted": [],
            "done": [],
        },
    )
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=2_000_000.0
    )
    assert any("author_only" in x and "flag" in x.lower() for x in lines), lines
    assert not any("recycleseat=" in x for x in lines), lines
    assert "!recycleseat" not in _outbox_text(tmp_path)
    assert list(recycleseat.queue_dir(install).glob("req-*.json")) == []
    doc = json.loads(gitclaim.queue_path(tmp_path).read_text(encoding="utf-8"))
    flagged = [r for r in doc["unaccepted"] if r.get("author_only_deadlock")]
    assert len(flagged) == 2


def test_fr5889_signature_change_does_not_re_recycle_same_seat(tmp_path, monkeypatch):
    """Seat-keyed pending/cooldown holds even when deadlock signature changes."""
    nick = "flamingo-90001"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 2_100_000.0
    # Bored-latency path still recycles; stamp pending for this seat.
    first = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now,
        install_root=install,
    )
    assert any("recycleseat=" in x for x in first), first
    assert _outbox_text(tmp_path).count("!recycleseat") == 1
    # Signature-like second heal soon after must not resend (awaiting ACK / cooldown).
    second = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now + 30,
        install_root=install,
    )
    assert not any("recycleseat=" in x for x in second), second
    assert _outbox_text(tmp_path).count("!recycleseat") == 1


def test_fr5889_skip_busy_working_on_seat(tmp_path, monkeypatch):
    nick = "flamingo-90002"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    # save_digest keeps work only for doing/offered (busy normalises to idle).
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": nick, "state": "doing", "work": "MRB SimonBarnett/bobiverse#1"}
    ]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 2_200_000.0
    lines = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},  # caller wrongly includes busy seat
        last_bored={nick: now - 938},
        now=now,
        install_root=install,
    )
    assert not any("recycleseat=" in x for x in lines), lines
    assert any("recycle_skipped:busy" in x for x in lines), lines
    assert "!recycleseat" not in _outbox_text(tmp_path)


def test_fr5889_no_bobiverse_channel(tmp_path, monkeypatch):
    nick = "flamingo-90003"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 2_300_000.0
    gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now,
        install_root=install,
    )
    text = _outbox_text(tmp_path)
    assert "PRIVMSG #bobiverse :" not in text
    assert "PRIVMSG #flamingo :!recycleseat" in text


def test_fr5889_ack_clears_outstanding_before_timeout(tmp_path, monkeypatch):
    nick = "flamingo-90004"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    now = 2_400_000.0
    gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now,
        install_root=install,
        cooldown_s=10.0,
    )
    assert _outbox_text(tmp_path).count("!recycleseat") == 1
    # ACK before cooldown expires unlocks a later send only after seat cooldown.
    gitclaim.note_recycleseat_ack(tmp_path, nick, now=now + 5)
    # Still inside seat cooldown window -> no resend.
    again = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now + 6,
        install_root=install,
        cooldown_s=10.0,
    )
    assert not any("recycleseat=" in x for x in again), again
    # After seat cooldown from ack_ts (+ cool), a new recycle is allowed.
    third = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - 938},
        now=now + 16,
        install_root=install,
        cooldown_s=10.0,
    )
    assert any("recycleseat=" in x for x in third), third
    assert _outbox_text(tmp_path).count("!recycleseat") == 2
