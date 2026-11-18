"""FR #8268: done-miss reminder must not hold BoredEmitter._cv across inject."""
from __future__ import annotations

import threading

import bob_worker as bw


def test_fr8268_remind_releases_cv_during_inject():
    em = bw.BoredEmitter(lambda: True, lambda _m: None, clock=lambda: 100.0)
    seen = []
    other_got = []

    def other() -> None:
        got = em._cv.acquire(timeout=0.4)
        other_got.append(got)
        if got:
            em._cv.release()

    def remind(key: str) -> None:
        t = threading.Thread(target=other)
        t.start()
        t.join()
        seen.append(key)

    em.done_miss_remind_fn = remind
    em._ack_open = True
    em._done_miss_armed_at = 0.0
    em.done_miss_grace_s = 0.0
    em._done_miss_key = "MRB SimonBarnett/bobiverse#1"
    with em._cv:
        em._fire_done_miss_remind(10.0)
    assert other_got == [True]
    assert seen == ["MRB SimonBarnett/bobiverse#1"]
    assert em._cv.acquire(timeout=0.2)
    em._cv.release()
