"""FR #9540: common depends_on.merge_depends_on_body must survive monitor path shadow.

Full tip build-jeeves collects monitor tests that ``sys.path.insert(0, tools/monitor)``.
A bare ``import depends_on`` then binds the monitor module (no merge_depends_on_body) and
reds FR #9469. gitclaim must load the common helper by file path.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import gitclaim
from repo_layout import REPO

MONITOR = REPO / "jeeves" / "tools" / "monitor"
COMMON_DEP = REPO / "common" / "scripts" / "depends_on.py"


def test_fr9540_common_depends_on_has_merge():
    assert COMMON_DEP.is_file()
    text = COMMON_DEP.read_text(encoding="utf-8")
    assert "def merge_depends_on_body" in text


def test_fr9540_gitclaim_stamp_under_monitor_path_shadow(monkeypatch):
    """Monitor-first path + poisoned sys.modules must not break giveup stamp."""
    mon = str(MONITOR)
    monkeypatch.syspath_prepend(mon)
    # Poison cache the way a prior monitor test would.
    sys.modules.pop("depends_on", None)
    import depends_on as shadowed  # noqa: F401

    assert shadowed.__file__ and "tools" in shadowed.__file__.replace("\\", "/")
    assert not hasattr(shadowed, "merge_depends_on_body")

    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8833",
        "body": "Depends-on: #8700\n",
        "labels": [],
    }
    refs = gitclaim.apply_depends_on_giveup_stamp(
        row, "blocked:depends-on #9354", patch_github=False
    )
    assert refs == [("SimonBarnett/bobiverse", 9354)]
    assert row["body"].startswith("Depends-on: #8700, #9354")


def test_fr9540_load_common_depends_on_helper():
    mod = gitclaim._load_common_depends_on()
    assert hasattr(mod, "merge_depends_on_body")
    new, changed = mod.merge_depends_on_body(
        "**Depends-on:** #1\n",
        [("SimonBarnett/bobiverse", 2)],
        repo="SimonBarnett/bobiverse",
    )
    assert changed
    assert new.startswith("Depends-on: #1, #2\n")
