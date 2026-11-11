"""Hostile pin docs/mrb-6658: FR #6655 build-work root + free-space preflight."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb


def test_mrb6658_resolve_root_alias_and_default():
    env = {
        "BOBIVERSE_BUILD_WORK": r"D:\Bobiverse\build-work",
        "ProgramData": r"C:\ProgramData",
    }
    assert bb.resolve_build_work_root(env) == Path(r"D:\Bobiverse\build-work")
    assert bb.resolve_build_work_root({"ProgramData": r"C:\ProgramData"}) == (
        Path(r"C:\ProgramData") / "Bobiverse" / "build-work"
    )


def test_mrb6658_work_dir_free_item_name_stable():
    import inspect

    src = inspect.getsource(bb.run_build_preflight)
    assert "work_dir_free" in src
    assert "build_work_min_free_gb" in src
