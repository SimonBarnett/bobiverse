"""FR #6256: deterministic idle-seat recovery for remediable author-only MRB deadlock.

Sole idle implementer seat blocked by exact-seat self_mrb (class of PR #6255 /
redqueen-16788) must get one bounded shop-only !recycleseat when worker evidence
is fresh and a new session would be eligible. Do not recycle for CodeRabbit-only
holds, stale worker state, OpenCode hostile-skip seats, busy/out-of-fuel, or when
an eligible non-author already exists.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import recycleseat

from test_fr5163_mrb_reviewer_deadlock import _mrb_row

NOW = datetime(2026, 11, 8, 20, 30, tzinfo=timezone.utc).timestamp()


def _outbox_text(tmp_path: Path) -> str:
    outbox = tmp_path / "chair-outbox.txt"
    if not outbox.is_file():
        outbox = Path(bobreport.fleet_digest_home(tmp_path)) / "chair-outbox.txt"
    return outbox.read_text(encoding="utf-8") if outbox.is_file() else ""


def _seed_idle(
    tmp_path,
    monkeypatch,
    nick: str,
    *,
    kind: str = "grok",
    updated: str = "2026-11-08T20:20:00Z",
    state: str = "idle",
    mid: str | None = None,
):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # Register before parse_seat_nick (unknown machines return None).
    guess = mid or nick.rsplit("-", 1)[0]
    registered_machines.save_registered(tmp_path, {guess})
    parsed = bobreport.parse_seat_nick(nick)
    assert parsed, f"parse_seat_nick failed for {nick!r} after register {guess!r}"
    mid = parsed[0]
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    pid = parsed[1]
    digest["machines"][mid]["worker_list"] = [
        {
            "nick": nick,
            "state": state,
            "work": "",
            "updated": updated,
            "kind": kind,
        }
    ]
    # Prefer pid-keyed workers for kind (save_digest may drop worker_list kind).
    digest["machines"][mid]["workers"] = {
        str(pid): {"state": state, "nick": nick, "kind": kind, "work": ""}
    }
    # Machine heartbeat alone must not count as fresh worker evidence.
    digest["machines"][mid]["lastSeen"] = "2026-11-08T20:30:00Z"
    bobreport.save_digest(tmp_path, digest)
    return nick


def test_fr6256_sole_author_idle_recycles_when_fresh(tmp_path, monkeypatch):
    """Single-seat MRB exclusion (PR #6255 class): one safe shop !recycleseat."""
    nick = "redqueen-16788"
    _seed_idle(tmp_path, monkeypatch, nick)
    now = NOW
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(
                    repo="SimonBarnett/bobiverse",
                    num=6255,
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
        tmp_path,
        install_root=install,
        now=now,
        last_activity={nick: now - 30},
    )
    assert any("author_only" in x and "flag" in x.lower() for x in lines), lines
    assert any("idle-recovery recycleseat=redqueen-16788" in x for x in lines), lines
    text = _outbox_text(tmp_path)
    assert "!recycleseat redqueen-16788 redqueen" in text
    assert "PRIVMSG #redqueen :" in text
    assert "PRIVMSG #bobiverse :" not in text
    # Local tray JSON may also be written; IRC shop path is required.
    assert list(recycleseat.queue_dir(install).glob("req-*.json"))
    saved = json.loads(gitclaim.queue_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["unaccepted"][0].get("author_only_deadlock") is True
    # Provenance stamps must survive (never erase implementer to manufacture independence).
    assert saved["unaccepted"][0].get("author_seat") == nick


def test_fr6256_stale_worker_state_no_recycle(tmp_path, monkeypatch):
    """Fresh machine lastSeen + stale/missing worker activity → no recycle."""
    nick = "redqueen-16788"
    _seed_idle(tmp_path, monkeypatch, nick, updated="2026-11-08T18:00:00Z")
    now = NOW
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(repo="SimonBarnett/bobiverse", num=6255, author=nick)
            ],
            "accepted": [],
            "done": [],
        },
    )
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        install_root=install,
        now=now,
        last_activity={},  # no fresh seat activity
    )
    assert any("author_only" in x and "flag" in x.lower() for x in lines), lines
    assert not any("recycleseat=" in x for x in lines), lines
    assert any("stale_worker" in x or "recycle_skipped" in x for x in lines), lines
    assert "!recycleseat" not in _outbox_text(tmp_path)


def test_fr6256_coderabbit_only_hold_no_recycle(tmp_path, monkeypatch):
    nick = "redqueen-16788"
    _seed_idle(tmp_path, monkeypatch, nick)
    now = NOW
    row = _mrb_row(repo="SimonBarnett/bobiverse", num=6255, author=nick)
    row["coderabbit"] = "pending"
    row["coderabbit_wait_since"] = now - 60
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        install_root=install,
        now=now,
        last_activity={nick: now - 10},
    )
    assert any("author_only" in x for x in lines), lines
    assert not any("recycleseat=" in x for x in lines), lines
    assert any("coderabbit" in x for x in lines), lines
    assert "!recycleseat" not in _outbox_text(tmp_path)


def test_fr6256_opencode_hostile_skip_no_recycle(tmp_path, monkeypatch):
    nick = "marchhare-2244"
    _seed_idle(tmp_path, monkeypatch, nick, kind="opencode")
    now = NOW
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(repo="SimonBarnett/bobiverse", num=6255, author=nick)
            ],
            "accepted": [],
            "done": [],
        },
    )
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        install_root=install,
        now=now,
        last_activity={nick: now - 10},
    )
    assert any("author_only" in x for x in lines), lines
    assert not any("recycleseat=" in x for x in lines), lines
    assert any("opencode" in x.lower() or "hostile" in x.lower() for x in lines), lines


def test_fr6256_busy_or_out_of_fuel_no_recycle(tmp_path, monkeypatch):
    nick = "redqueen-16788"
    _seed_idle(tmp_path, monkeypatch, nick)
    now = NOW
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(repo="SimonBarnett/bobiverse", num=6255, author=nick)
            ],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1",
                    "accepted_by": nick,
                }
            ],
            "done": [],
        },
    )
    # Accepted seat is not idle for free_seat_nicks — force idle set to include nick
    # while working_on / accepted blocks recycle.
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        idle={nick},
        live={nick},
        install_root=install,
        now=now,
        last_activity={nick: now - 10},
    )
    # With only author-blocked MRB and forced idle, heal may still flag; recycle must skip busy.
    if lines:
        assert not any(
            "idle-recovery recycleseat=" in x for x in lines
        ), lines
    assert "!recycleseat" not in _outbox_text(tmp_path)

    # Out-of-fuel mark (reset recovery + pending so only fuel gate applies)
    gitclaim._save_idle_seat_recovery_state(tmp_path, {"machines": {}})
    gitclaim._save_recycleseat_pending(tmp_path, {"seats": {}})
    gitclaim.note_seat_out_of_fuel(tmp_path, nick, reason="out-of-fuel")
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(repo="SimonBarnett/bobiverse", num=6260, author=nick)
            ],
            "accepted": [],
            "done": [],
        },
    )
    # Clear prior deadlock cooldown by using a new now far ahead + new signature via num
    lines2 = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        idle={nick},
        live={nick},
        install_root=install,
        now=now + 10_000,
        last_activity={nick: now + 10_000 - 5},
        cooldown_s=1.0,
    )
    assert not any("idle-recovery recycleseat=" in x for x in lines2), lines2


def test_fr6256_eligible_other_seat_no_deadlock(tmp_path, monkeypatch):
    """Available eligible reviewer → no author_only heal / no recycle."""
    author = "redqueen-16788"
    other = "flamingo-99"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen", "flamingo"})
    digest = bobreport.empty_digest()
    for nick in (author, other):
        mid = bobreport.parse_seat_nick(nick)[0]
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {"nick": nick, "state": "idle", "kind": "grok"}
        ]
    bobreport.save_digest(tmp_path, digest)
    now = NOW
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(repo="SimonBarnett/bobiverse", num=6255, author=author)
            ],
            "accepted": [],
            "done": [],
        },
    )
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        now=now,
        last_activity={author: now - 10, other: now - 10},
    )
    assert lines == []
    assert "!recycleseat" not in _outbox_text(tmp_path)


def test_fr6256_idempotent_second_tick_no_duplicate(tmp_path, monkeypatch):
    nick = "redqueen-16788"
    _seed_idle(tmp_path, monkeypatch, nick)
    now = NOW
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                _mrb_row(repo="SimonBarnett/bobiverse", num=6255, author=nick)
            ],
            "accepted": [],
            "done": [],
        },
    )
    install = tmp_path / "install"
    install.mkdir()
    first = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        install_root=install,
        now=now,
        last_activity={nick: now - 10},
    )
    assert any("idle-recovery recycleseat=" in x for x in first), first
    second = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path,
        install_root=install,
        now=now + 30,
        last_activity={nick: now + 20},
    )
    # Signature cooldown on deadlock heal → empty, or soft skip without second send.
    assert not any("idle-recovery recycleseat=" in x for x in second), second
    assert _outbox_text(tmp_path).count("!recycleseat") == 1


def test_fr6256_attempt_cap_stops_churn(tmp_path, monkeypatch):
    nick = "redqueen-16788"
    _seed_idle(tmp_path, monkeypatch, nick)
    install = tmp_path / "install"
    install.mkdir()
    base = NOW
    sends = 0
    for i in range(6):
        # Unique signature each attempt so deadlock cooldown does not hide the cap.
        gitclaim._write_queue(
            gitclaim.queue_path(tmp_path),
            {
                "v": 1,
                "unaccepted": [
                    _mrb_row(
                        repo="SimonBarnett/bobiverse",
                        num=7000 + i,
                        author=nick,
                    )
                ],
                "accepted": [],
                "done": [],
            },
        )
        # Clear seat pending so ACK-wait does not block; cap is machine attempts.
        gitclaim._save_recycleseat_pending(tmp_path, {"seats": {}})
        now = base + (i * 10_000)
        lines = gitclaim.heal_mrb_reviewer_deadlock(
            tmp_path,
            install_root=install,
            now=now,
            last_activity={nick: now - 5},
            cooldown_s=1.0,
        )
        if any("idle-recovery recycleseat=" in x for x in lines):
            sends += 1
            gitclaim.note_recycleseat_ack(tmp_path, nick, now=now + 1)
    assert sends == gitclaim.IDLE_SEAT_RECOVERY_MAX_ATTEMPTS
    assert _outbox_text(tmp_path).count("!recycleseat") == sends
