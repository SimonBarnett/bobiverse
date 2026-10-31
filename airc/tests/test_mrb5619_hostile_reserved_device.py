"""MRB #5619 hostile pins for FR #5610 reserved-device sandbox."""
from __future__ import annotations

import pytest

import airc_jobs as jobs


def test_mrb5619_com10_and_combo_are_not_devices(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    dest = jobs.resolve_sandbox_path(drop, "COM10.txt")
    assert dest.name.lower() == "com10.txt"
    dest2 = jobs.resolve_sandbox_path(drop, "combo.txt")
    assert dest2.name == "combo.txt"


def test_mrb5619_trailing_dot_space_still_reserved(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    for raw in ("COM1.", "nul. ", "LPT9.log"):
        with pytest.raises(jobs.JobProtocolError) as ei:
            jobs.resolve_sandbox_path(drop, raw)
        assert ei.value.code == "bad_path"
