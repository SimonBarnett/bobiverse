"""MRB #5374: service runner wait=False and still GPO-then-fill-holes."""
from __future__ import annotations

import inspect

import airc_extension as ex


def test_mrb5374_wait_false_keeps_fill_holes_worker():
    src = inspect.getsource(ex.service_extension_runner)
    compact = "".join(src.split())
    assert "wait=False" in compact
    assert "wait=True" not in compact
    assert "extension_gpo_then_fill_holes" in src
    assert callable(ex.extension_gpo_then_fill_holes)
