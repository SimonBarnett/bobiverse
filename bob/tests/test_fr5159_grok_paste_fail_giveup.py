"""FR #5159: Grok ACK-on-receipt must not skip paste-fail recovery (regression of #4510).

marchhare-29688 ACKed then paste failed; InjectRecovery returned ``acked`` because
``block_on_receipt_ack`` was True for grok. The seat sat on the job for hours.
"""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
from test_fr2884_startup_turn_ready import _sup
from test_fr4510_cursor_submit_verify_giveup import ASSIGN, GIVEUP, _cursor_recovery


def test_fr5159_receipt_ack_still_repastes_then_giveup():
    """Grok/Cursor receipt ACK is not a running turn; retry once then GIVEUP."""
    pasted: list[str] = []

    def reinject(line, cb):
        pasted.append(line)
        cb()
        return True

    rec, state = _cursor_recovery(reinject=reinject, acked=True)
    rec.block_on_receipt_ack = False
    rec.giveup_on_fail = True
    rec.on_failed(ASSIGN, attempt=1)
    assert pasted == [ASSIGN]
    assert state["outbox"] == [GIVEUP]


def test_fr5159_successful_retry_does_not_giveup():
    pasted: list[str] = []

    def reinject(line, cb):
        pasted.append(line)
        return True

    rec, state = _cursor_recovery(reinject=reinject, acked=True)
    rec.block_on_receipt_ack = False
    rec.giveup_on_fail = True
    assert rec.on_failed(ASSIGN, attempt=1) == "retried"
    assert pasted == [ASSIGN]
    assert state["outbox"] == []


def test_fr5159_supervisor_grok_uses_giveup_not_receipt_block(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY_GIVEUP_GRACE_S", "0")
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch, kind="grok")
    rec = sup._inject_recovery()
    assert rec.giveup_on_fail is True
    assert rec.block_on_receipt_ack is False
    sup.ack_miss.note_inject(ASSIGN, 0.0, own_nick=sup.nick)
    relay.last_unacked = ASSIGN
    res = rec.on_failed(ASSIGN, attempt=2)
    assert res == "giveup"
    ob = bw.outbox_path_for_run(tmp_path)
    assert GIVEUP in ob.read_text(encoding="utf-8")
    assert any("submit-verify failed twice" in m or "GIVEUP" in m for m in logs)


def test_fr5159_supervisor_cursor_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY_GIVEUP_GRACE_S", "0")
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch, kind="cursor")
    rec = sup._inject_recovery()
    assert rec.giveup_on_fail is True
    assert rec.block_on_receipt_ack is False


def test_fr5159_source_and_skill_pin_grok():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    fn = src[src.index("def _inject_recovery"):]
    fn = fn[: fn.index("\n    def _inject_line")]
    assert "FR #5159" in fn
    assert "is_grok" in fn
    assert "giveup_on_fail=receipt_ack" in fn or "giveup_on_fail=" in fn
    skill = (Path(__file__).resolve().parents[2] / "bob/.grok/skills/bobiverse-bob-worker/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #5159" in skill
    assert "Grok" in skill and "receipt" in skill.lower()
