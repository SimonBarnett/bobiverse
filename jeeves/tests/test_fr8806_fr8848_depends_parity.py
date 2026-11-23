"""FR #9193: monitor parse_depends agrees with depends_on_parse.resolve_depends_ref.

Never use bare ``import depends_on`` — that can bind the common helper or the
monitor module depending on PYTHONPATH order. Load the monitor by file path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from repo_layout import REPO

# Prefer the named common helper (FR #8806).
sys.path.insert(0, str(REPO / "common" / "scripts"))
import depends_on_parse  # noqa: E402


def _load_monitor():
    path = REPO / "jeeves" / "tools" / "monitor" / "depends_on.py"
    spec = importlib.util.spec_from_file_location("jeeves_monitor_depends_on_fr9193", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Sibling _common must resolve from the monitor directory.
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        if str(path.parent) in sys.path:
            sys.path.remove(str(path.parent))
    return mod


_MON = None


def _monitor():
    global _MON
    if _MON is None:
        _MON = _load_monitor()
    return _MON


def test_parity_relative_and_qualified_keys():
    mon = _monitor()
    homes = ("SimonBarnett/bobiverse", "SimonBarnett/a-search")
    for home in homes:
        for token in ("#9", "other/repo#9"):
            resolved = depends_on_parse.resolve_depends_ref(home, token)
            refs = mon.parse_depends(f"Depends-on: {token}\n", home)
            assert len(refs) == 1, (home, token, refs)
            key = f"{refs[0][0]}#{refs[0][1]}"
            assert key == resolved, (home, token, key, resolved)


def test_parity_bold_label_matches_relative():
    mon = _monitor()
    home = "SimonBarnett/bobiverse"
    refs = mon.parse_depends("**Depends-on:** #9\n", home)
    assert refs == [("SimonBarnett/bobiverse", 9)]
    assert depends_on_parse.resolve_depends_ref(home, "#9") == "SimonBarnett/bobiverse#9"
