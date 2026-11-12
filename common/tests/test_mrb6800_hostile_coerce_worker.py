"""MRB #6800: worker survives coerce even when nick differs; done list too."""
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


def test_mrb6800_worker_without_nick():
    out = gitclaim._coerce_row(_row(worker="walrus-9"))
    assert out is not None
    assert out["worker"] == "walrus-9"
    assert "nick" not in out


def test_mrb6800_done_reload_keeps_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [_row(worker="flamingo-1", nick="flamingo-1", result="PASS")],
        },
    )
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert done and done[0]["worker"] == "flamingo-1"
