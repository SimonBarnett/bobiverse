"""FR #1520: focus is per-repo; refuse / prune redundant owner/repo#N items."""
from __future__ import annotations

import focus_ignore as fi


def test_set_item_refused_when_repo_already_focused(tmp_path):
    home = tmp_path
    assert fi.dispatch(home, "simon", "simon", "!focus high SimonBarnett/bobiverse", ops=True)[0].startswith(
        "focus: SimonBarnett/bobiverse"
    )
    lines = fi.dispatch(home, "simon", "simon", "!focus SimonBarnett/bobiverse#1102", ops=True)
    assert any("per-repo" in ln.lower() or "1520" in ln or "skipped" in ln.lower() for ln in lines)
    doc = fi.load_focus(home)
    assert "SimonBarnett/bobiverse#1102" not in (doc.get("items") or {})
    assert "simonbarnett/bobiverse#1102" not in {k.lower() for k in (doc.get("items") or {})}


def test_prune_redundant_items_when_repo_focused(tmp_path):
    home = tmp_path
    fi.dispatch(home, "simon", "simon", "!focus high SimonBarnett/bobiverse", ops=True)
    # Bypass refusal to seed a stale item (legacy / ear spam).
    doc = fi.load_focus(home)
    doc["items"]["SimonBarnett/bobiverse#1102"] = {
        "rank": 6,
        "repo": "SimonBarnett/bobiverse",
        "id": "#1102",
        "label": "high",
        "ts": "2026-10-04T00:00:00Z",
    }
    fi.save_focus(home, doc)
    n = fi.prune_redundant_focus_items(home)
    assert n == 1
    doc2 = fi.load_focus(home)
    assert not (doc2.get("items") or {})


def test_item_focus_still_allowed_when_repo_not_focused(tmp_path):
    home = tmp_path
    lines = fi.dispatch(home, "simon", "simon", "!focus SimonBarnett/other#9", ops=True)
    assert lines[0].startswith("focus: item")
    doc = fi.load_focus(home)
    assert any(k.lower().endswith("#9") for k in (doc.get("items") or {}))


def test_set_repo_prunes_existing_redundant_items(tmp_path):
    home = tmp_path
    assert fi.dispatch(home, "simon", "simon", "!focus SimonBarnett/bobiverse#42", ops=True)[0].startswith(
        "focus: item"
    )
    lines = fi.dispatch(home, "simon", "simon", "!focus high SimonBarnett/bobiverse", ops=True)
    assert lines[0].startswith("focus: SimonBarnett/bobiverse")
    assert any("pruned" in ln.lower() or "1520" in ln for ln in lines)
    doc = fi.load_focus(home)
    assert not (doc.get("items") or {})
