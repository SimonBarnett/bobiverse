"""FR #8536: digest queue summary flags healthy idle vs hung (needs_human-only)."""
from __future__ import annotations

import bobreport


def test_fr8536_public_queue_needs_human_only():
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#1",
            "number": "1",
            "needs_human": True,
            "title": "human",
            "labels": ["feature-request"],
            "line": "FR SimonBarnett/bobiverse#1",
        },
        {
            "repo": "SimonBarnett/a-search",
            "task": "FR",
            "id": "#2",
            "number": "2",
            "needs_human": True,
            "title": "human2",
            "labels": ["feature-request"],
            "line": "FR SimonBarnett/a-search#2",
        },
    ]
    pub = bobreport.summarize_public_queue(rows, [])
    assert pub["unaccepted_count"] == 2
    assert pub["needs_human_count"] == 2
    assert pub["offerable_count"] == 0
    assert pub["queue_needs_human_only"] is True


def test_fr8536_public_queue_offerable_when_ungated():
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#99",
            "number": "99",
            "title": "real",
            "labels": ["feature-request"],
            "line": "FR SimonBarnett/bobiverse#99",
        }
    ]
    pub = bobreport.summarize_public_queue(rows, [])
    assert pub["unaccepted_count"] == 1
    assert pub["needs_human_count"] == 0
    assert pub["offerable_count"] >= 1
    assert pub["queue_needs_human_only"] is False


def test_fr8536_public_queue_wires_summary_keys():
    import inspect

    src = inspect.getsource(bobreport._public_queue)
    assert "summarize_public_queue" in src
    assert "offerable_count" in src or "summarize_public_queue" in src