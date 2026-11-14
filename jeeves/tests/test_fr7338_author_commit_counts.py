"""FR #7338: MRB rows store per-seat commit counts from GitHub authors."""
from __future__ import annotations

import gitclaim
import registered_machines


def _ready(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"flamingo", "marchhare"})


def test_fr7338_payload_counts_each_commit_once_per_seat(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch)
    payload = [
        {"commit": {"author": {"name": "flamingo-1"}, "committer": {"name": "flamingo-1"}}},
        {"commit": {"author": {"name": "flamingo-1"}, "committer": {"name": "GitHub"}}},
        {"commit": {"author": {"name": "marchhare-2"}, "committer": {"name": "marchhare-2"}}},
        {"commit": {"author": {"name": "SimonBarnett"}, "committer": {"name": "SimonBarnett"}}},
    ]
    assert gitclaim.seat_commit_counts_from_payload(payload) == {
        "flamingo-1": 2,
        "marchhare-2": 1,
    }


def test_fr7338_stamp_survives_queue_reload(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [{
                "task": "MRB",
                "repo": "SimonBarnett/bobiverse",
                "id": "#7311",
                "url": "https://github.com/SimonBarnett/bobiverse/pull/7311",
            }],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(repo, num):
        assert repo == "SimonBarnett/bobiverse"
        assert str(num).lstrip("#") == "7311"
        return {"flamingo-1": 1, "marchhare-2": 3}

    n = gitclaim.stamp_mrb_author_commit_counts(
        tmp_path,
        gitclaim.load_unaccepted(tmp_path),
        fetch,
    )
    assert n == 1
    reloaded = gitclaim.load_unaccepted(tmp_path)[0]
    assert reloaded["author_commit_counts"]["marchhare-2"] == 3
    assert reloaded["author_commit_counts"]["flamingo-1"] == 1
