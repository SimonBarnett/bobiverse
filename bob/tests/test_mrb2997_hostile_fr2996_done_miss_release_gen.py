"""Hostile MRB pins for FR #2996 / PR #2997: done-miss release_gen + no wait(0) spin."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

ROOT = Path(__file__).resolve().parents[1]
WORKER_PY = ROOT / "scripts" / "bob_worker.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
PRODUCT = ROOT / "tests" / "test_fr2996_done_miss_release_gen.py"


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb2997_product_test_module_present():
    assert PRODUCT.is_file()
    t = _t(PRODUCT)
    assert "FR #2996" in t
    assert "_release_gen == e._turn_gen" in t or "_release_gen ==" in t
    assert "done-miss" in t
    assert "nak" in t


def test_mrb2997_done_miss_release_sets_release_gen_contiguous():
    text = _t(WORKER_PY)
    # Contiguous window around the done-miss release branch (assignment before log).
    assert "FR #2996" in text
    i = text.index("_done_miss_release_pending = True")
    window = text[i : i + 700]
    assert "_release_gen = self._turn_gen" in window
    assert "still no DONE for" in window
    assert "FR #2996" in window


def test_mrb2997_run_clamps_past_due_wait_contiguous():
    text = _t(WORKER_PY)
    run_body = text.split("def _run(self)")[1].split("STALE_BUILD")[0]
    assert "FR #2996" in run_body
    assert "0.5" in run_body
    assert "wait(0)" in run_body or "busy-loop" in run_body or "busy-wait" in run_body


def test_mrb2997_skill_fr2996_contiguous():
    t = _t(SKILL)
    assert "FR #2996" in t
    assert "_release_gen = _turn_gen" in t or "_release_gen = `_turn_gen`" in t or "_release_gen" in t
    assert "done-miss" in t
    # Troubleshooting row + harvested lesson.
    assert "stale `_release_gen`" in t or "stale _release_gen" in t
    assert "wait(0)" in t or "spins" in t or "spin" in t


def test_mrb2997_behavioral_nak_after_prior_done_then_done_miss():
    """Re-assert product acceptance on tip (hostile re-run)."""
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(
        clock,
        harvest_hold_s=5.0,
        done_miss_grace_s=20.0,
        idle_s=120.0,
        repeat_s=180.0,
        nak_s=1.0,
    )
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.turn_started(at=clock())
    e.on_outbox("ACK MRB o/r#1")
    e.on_outbox("DONE MRB o/r#1 FAIL https://example.com/pull/1")
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done" for _, r in e.sent), clock), (e.sent, logs)
    e.turn_started(at=clock())
    e.on_outbox("ACK MRB o/r#2994")
    e.turn_ended(at=clock())
    clock.advance(21.0)
    assert _wait(lambda: len(reminds) == 1, clock), (reminds, logs)
    e.turn_started(at=clock())
    n0 = len(sent)
    e.turn_ended(at=clock())
    assert _wait(lambda: any(r == "done-miss" for _, r in e.sent[n0:]), clock), (e.sent[n0:], logs)
    assert e._release_gen == e._turn_gen
    n1 = len(sent)
    e.nak()
    clock.advance(1.2)
    assert _wait(
        lambda: any(r in ("nak", "idle") for _, r in e.sent[n1:]),
        clock,
        timeout=3.0,
    ), (e.sent[n1:], e._release_gen, e._turn_gen)
    e.stop()
    assert "FR #2996" in _t(Path(bw.__file__))
