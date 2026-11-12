"""FR #6770: gitclaim._coerce_row keeps stored worker on reload."""
from __future__ import annotations

import gitclaim


def _row(**extra):
    base = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#6770",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#6770",
        "title": "keep worker",
    }
    base.update(extra)
    return base


def test_fr6770_coerce_keeps_worker_and_nick():
    out = gitclaim._coerce_row(_row(worker="flamingo-1", nick="flamingo-1"))
    assert out is not None
    assert out["worker"] == "flamingo-1"
    assert out["nick"] == "flamingo-1"


def test_fr6770_load_unaccepted_accepted_keep_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [_row(worker="flamingo-1")],
            "accepted": [_row(id="#6771", worker="redqueen-2", nick="other")],
            "done": [],
        },
    )
    un = gitclaim.load_unaccepted(tmp_path)[0]
    acc = gitclaim.load_accepted(tmp_path)[0]
    assert un["worker"] == "flamingo-1"
    assert acc["worker"] == "redqueen-2"
    assert acc["nick"] == "other"
