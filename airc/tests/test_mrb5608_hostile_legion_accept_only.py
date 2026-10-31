"""MRB #5608 hostile pin: LEGION accept reply is accept-only (FR #5602 / #5583)."""
from __future__ import annotations

import airc_legion as lg


def test_mrb5608_accept_reply_has_no_done_or_exit():
    res = lg.run_legion_verb(
        target="flamingo",
        worker=lambda target, whatif=False, **kw: {"ok": True},
        wait=False,
        job_id="deadbeef",
    )
    assert res.reply.startswith("LEGION accepted")
    assert "id=deadbeef" in res.reply
    assert "DONE" not in res.reply
    assert "exit=" not in res.reply


def test_mrb5608_mrb5474_pins_accept_only_asserts():
    from pathlib import Path
    text = Path(lg.__file__).resolve().parents[1].joinpath(
        "tests", "test_mrb5474_hostile_legion_credman_off_irc.py"
    ).read_text(encoding="utf-8")
    assert 'assert "exit=" not in res.reply' in text
    assert 'assert "DONE" not in res.reply' in text
    assert 'assert "exit=0" in res.reply' not in text
