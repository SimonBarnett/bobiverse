"""MRB #5044 hostile pins for FR #5042 LiveStateTouched soft ceiling."""
from __future__ import annotations

import bobiverse_build as bb


def test_mrb5044_default_soft_ceiling_is_fifteen():
    import inspect
    sig = inspect.signature(bb.live_state_damage)
    assert sig.parameters["max_lost"].default == 15


def test_mrb5044_small_queue_empty_still_mass_wipe():
    before = {"/q": {f"k{i}" for i in range(7)}}
    after = {"/q": set()}
    assert bb.live_state_damage(before, after) == ["/q lost 7"]


def test_mrb5044_majority_of_sizeable_queue_is_damage():
    keys = {f"k{i}" for i in range(12)}
    before = {"/q": keys}
    after = {"/q": set(list(keys)[:3])}  # lost 9 of 12 (> half)
    assert bb.live_state_damage(before, after) == ["/q lost 9"]
