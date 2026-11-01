"""MRB #5474 hostile pins: LEGION CredRead stays off the IRC accept path (FR #5389)."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg


def test_mrb5474_run_legion_verb_does_not_call_credman_on_accept():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise AssertionError("credman must not run on accept")

    def worker(target, whatif=False, **kw):
        # worker may receive credman kw but accept path must not invoke it
        return {"ok": True, "error": None}

    res = lg.run_legion_verb(
        target="box1",
        credman=boom,
        worker=worker,
        wait=False,
        job_id="aabbccdd",
    )
    assert calls["n"] == 0
    assert "LEGION accepted" in res.reply
    # FR #5583 / #5602: accept line has no DONE; exit comes after the log.
    assert "exit=" not in res.reply
    assert "DONE" not in res.reply


def test_mrb5474_wait_true_surfaces_worker_error_without_forced_126():
    def worker(target, whatif=False, **kw):
        return {"ok": False, "error": "auth_failed", "identity": "passed"}

    res = lg.run_legion_verb(
        target="box1",
        worker=worker,
        wait=True,
        job_id="aabbccdd",
    )
    assert "LEGION accepted" in res.reply or "auth_failed" in (res.error or "")
    assert "126" not in res.reply.split()


def test_mrb5474_source_pins_fr5389_off_accept():
    src = Path(lg.__file__).read_text(encoding="utf-8")
    assert "FR #5389: CredRead lives here" in src
    # accept path must not call default_legion_credman before spawning worker
    # (contiguous window around run_legion_verb)
    i = src.index("def run_legion_verb")
    window = src[i : i + 1800]
    assert "default_legion_credman" not in window.split("if wait:")[0]