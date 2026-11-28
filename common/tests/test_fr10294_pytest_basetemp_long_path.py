"""FR #10294: long Windows job-worktree paths need a short pytest basetemp."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import crash_report


def test_fr10294_needs_short_when_temp_long(monkeypatch):
    if not sys.platform.startswith("win"):
        return
    wt = r"C:\Users\Administrator\.grok\bob-bridge\worktrees\bobiverse\fr-10294\.bob\tmp"
    monkeypatch.setenv("TEMP", wt)
    monkeypatch.setenv("TMP", wt)
    cfg = SimpleNamespace(rootpath=Path(r"C:\cmr"))
    assert crash_report.pytest_basetemp_needs_short_windows_path(cfg) is True


def test_fr10294_short_pt_parent_for_job_paths():
    if not sys.platform.startswith("win"):
        return
    parent = crash_report.isolated_pytest_basetemp_parent(short=True)
    assert str(parent).replace("\\", "/").startswith("C:/pt")