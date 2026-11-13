"""MRB #6998: pin Windows pathlib ``Path("C:") / "Users"`` drive-relative trap.

Product fix lives on PR #6998 (``bobreport._system_drive_root``). This file is
import-free of that helper so it can land on main before or after the fix.
Never logs secrets.
"""
from __future__ import annotations

from pathlib import Path


def test_mrb6998_bare_c_colon_join_is_not_c_backslash_users():
    joined = Path("C:") / "Users" / "Administrator"
    text = str(joined).replace("/", "\\")
    assert joined.is_absolute() is False
    assert text.startswith("C:Users")
    assert not text.upper().startswith("C:\\USERS\\")


def test_mrb6998_rooted_c_backslash_join_is_absolute_users():
    joined = Path("C:\\") / "Users" / "Administrator"
    text = str(joined).replace("/", "\\")
    assert joined.is_absolute() is True
    assert text.upper().startswith("C:\\USERS\\")
    assert "C:Users" not in text
