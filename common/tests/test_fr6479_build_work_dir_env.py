"""FR #6479: BOBIVERSE_BUILD_WORK_DIR overrides default BUILD work dir."""
from __future__ import annotations

from pathlib import Path

import run_bobiverse_build as rbb


def test_fr6479_work_dir_arg_wins_over_env():
    env = {
        "BOBIVERSE_BUILD_WORK_DIR": r"D:\build-work",
        "ProgramData": r"C:\ProgramData",
    }
    got = rbb.resolve_build_work_dir(
        "0.1.99",
        work_dir_arg=r"E:\explicit\work",
        env=env,
    )
    assert got == Path(r"E:\explicit\work")


def test_fr6479_env_used_when_no_arg():
    env = {
        "BOBIVERSE_BUILD_WORK_DIR": r"D:\ai\bobiverse-build-work",
        "ProgramData": r"C:\ProgramData",
    }
    got = rbb.resolve_build_work_dir("0.1.99", work_dir_arg="", env=env)
    assert got == Path(r"D:\ai\bobiverse-build-work") / "0.1.99"


def test_fr6479_default_unchanged_when_neither():
    env = {"ProgramData": r"C:\ProgramData"}
    got = rbb.resolve_build_work_dir("0.1.99", work_dir_arg="", env=env)
    assert got == Path(r"C:\ProgramData") / "Bobiverse" / "build-work" / "0.1.99"


def test_fr6479_blank_env_falls_back_to_default():
    env = {"BOBIVERSE_BUILD_WORK_DIR": "  ", "ProgramData": r"C:\ProgramData"}
    got = rbb.resolve_build_work_dir("1.2.3", work_dir_arg="", env=env)
    assert got == Path(r"C:\ProgramData") / "Bobiverse" / "build-work" / "1.2.3"
