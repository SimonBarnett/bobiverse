"""FR #6472: OpenCode DONE for current job must send; refuse reasons must be logged."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import bob_worker as bw  # noqa: E402
import opencode_seat_contract as c  # noqa: E402

# Exact DONE form from MarchHare FR #6468 / PR #6469 (issue narrative).
DONE_6468 = (
    "DONE FR SimonBarnett/bobiverse#6468 "
    "https://github.com/SimonBarnett/bobiverse/pull/6469"
)
KEY_6468 = "FR SimonBarnett/bobiverse#6468"
SHOP = "#marchhare"


def test_fr6468_done_form_allowed_and_short_repo_variants():
    assert c.opencode_outbox_line_allowed(DONE_6468, job_key=KEY_6468, shop=SHOP)
    assert c.opencode_outbox_refuse_reason(DONE_6468, job_key=KEY_6468, shop=SHOP) is None
    assert c.opencode_outbox_line_allowed(
        "DONE FR #6468 https://github.com/SimonBarnett/bobiverse/pull/6469",
        job_key=KEY_6468,
        shop=SHOP,
    )
    assert c.opencode_outbox_line_allowed(
        "DONE FR bobiverse#6468 https://github.com/SimonBarnett/bobiverse/pull/6469",
        job_key=KEY_6468,
        shop=SHOP,
    )
    assert c.opencode_outbox_line_allowed(
        f"PRIVMSG {SHOP} :{DONE_6468}",
        job_key=KEY_6468,
        shop=SHOP,
    )
    assert c.opencode_outbox_line_allowed(
        DONE_6468 + " opened PR",
        job_key=KEY_6468,
        shop=SHOP,
    )


def test_wrong_job_done_refused_as_job_key_mismatch():
    reason = c.opencode_outbox_refuse_reason(
        "DONE FR SimonBarnett/bobiverse#9999 https://example/x",
        job_key=KEY_6468,
        shop=SHOP,
    )
    assert reason == "job-key mismatch"
    assert c.opencode_outbox_refuse_reason(
        "PRIVMSG #other :DONE FR SimonBarnett/bobiverse#6468 https://x",
        job_key=KEY_6468,
        shop=SHOP,
    ) == "wrong channel"
    assert c.opencode_outbox_refuse_reason(
        "PRIVMSG #marchhare :hello world",
        job_key=KEY_6468,
        shop=SHOP,
    ) == "malformed"


def test_may_send_job_outbox_sends_6468_done_and_logs_mismatch(tmp_path: Path):
    logs: list[str] = []
    bored = bw.BoredEmitter(send=lambda: True, log=logs.append)
    bored._ack_open = True
    bored._ack_job_key = KEY_6468

    sup = bw.Supervisor.__new__(bw.Supervisor)
    sup._opencode_job_key = KEY_6468
    sup._opencode_job_outbox = tmp_path / ".bob" / "outbox.txt"
    sup.machine = "marchhare"
    sup.irc = MagicMock()
    sup.irc.shop = SHOP
    sup.bored = bored

    assert bw.Supervisor.may_send_job_outbox(sup, DONE_6468) is True
    assert bw.Supervisor.may_send_job_outbox(sup, "DONE FR #6468 https://x/pull/1") is True
    decision = bw.Supervisor.may_send_job_outbox(
        sup, "DONE FR SimonBarnett/bobiverse#1 https://x"
    )
    assert decision == (False, "job-key mismatch")


def test_drain_logs_job_key_mismatch_not_stale_replay(tmp_path: Path):
    job = tmp_path / "wt"
    job.mkdir()
    ob = c.ensure_opencode_bob_outbox(job)
    ob.write_text(
        "PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#9999 https://x\n",
        encoding="utf-8",
    )
    logs: list[str] = []
    said: list[str] = []
    irc = MagicMock()
    irc.alive = True
    irc.shop = SHOP
    irc.say = lambda target, text: said.append(text) or True

    def may_send(payload: str):
        reason = c.opencode_outbox_refuse_reason(
            payload, job_key=KEY_6468, shop=SHOP
        )
        if reason:
            return (False, reason)
        return True

    n = bw.drain_outbox(ob, irc, logs.append, may_send=may_send)
    assert n == 0
    assert said == []
    assert any("dropped job-key mismatch" in m for m in logs), logs
    assert not any("dropped stale replay" in m for m in logs)


def test_drain_sends_current_job_done_6468_form(tmp_path: Path):
    job = tmp_path / "wt"
    job.mkdir()
    ob = c.ensure_opencode_bob_outbox(job)
    line = f"PRIVMSG {SHOP} :{DONE_6468}"
    ob.write_text(line + "\n", encoding="utf-8")
    logs: list[str] = []
    said: list[str] = []
    irc = MagicMock()
    irc.alive = True
    irc.shop = SHOP
    irc.say = lambda target, text: said.append(text) or True

    def may_send(payload: str):
        reason = c.opencode_outbox_refuse_reason(
            payload, job_key=KEY_6468, shop=SHOP
        )
        if reason:
            return (False, reason)
        return True

    n = bw.drain_outbox(ob, irc, logs.append, may_send=may_send)
    assert n >= 1
    assert any("DONE FR SimonBarnett/bobiverse#6468" in t for t in said)
    assert any("outbox: sent" in m for m in logs)


def test_finished_job_ack_still_dropped_with_reason():
    bored = bw.BoredEmitter(send=lambda: True, log=lambda *_: None)
    bored._ack_open = False
    bored.on_outbox("ACK FR SimonBarnett/bobiverse#6468")
    bored.on_outbox(DONE_6468)
    assert bored.outbox_ack_refuse_reason("ACK FR SimonBarnett/bobiverse#6468") == (
        "finished-job ACK replay"
    )
    assert bored.should_forward_outbox("ACK FR SimonBarnett/bobiverse#6468") is False
    assert bored.should_forward_outbox(DONE_6468) is True


def test_duplicate_ack_while_open_still_dropped():
    bored = bw.BoredEmitter(send=lambda: True, log=lambda *_: None)
    bored._ack_open = True
    bored._ack_job_key = KEY_6468
    assert bored.outbox_ack_refuse_reason("ACK FR SimonBarnett/bobiverse#6468") == (
        "duplicate ACK"
    )
    assert bored.should_forward_outbox("ACK FR SimonBarnett/bobiverse#6468") is False