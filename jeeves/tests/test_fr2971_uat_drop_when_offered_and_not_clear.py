"""FR #2971: via-intake feature-request blocks repo UAT; sticky offered UAT drops.

#2970 title starts with ``Harvest …`` so HARVEST_TITLE_RE wrongly treated it as a
non-blocking harvest receipt. Chair offered UAT #0 while that FR was open.
Also: resync must drop unaccepted UAT when the repo is not clear even if offered_to
is set (sticky offer after clear broke).
"""
from __future__ import annotations

import pytest

import gitclaim

from test_fr628_repo_focus import _gh, _merged_pr, _now_iso, _uats


@pytest.fixture
def _home(tmp_path, monkeypatch):
    import bobreport
    import registered_machines

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    registered_machines.save_registered(tmp_path, {"ionos", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def test_fr2971_via_intake_feature_request_blocks_repo_uat_despite_harvest_word_title():
    assert (
        gitclaim.issue_blocks_repo_uat(
            title="Harvest re-promotes FAIL-supersede process lessons into harvest (twin MRB loop)",
            labels=("feature-request", "via-intake"),
        )
        is True
    )
    # Colon-form harvest receipts still do not block.
    assert (
        gitclaim.issue_blocks_repo_uat(title="harvest: skill notes", labels=("via-intake",))
        is False
    )


def test_fr2971_offered_uat_dropped_when_blocking_fr_opens(_home):
    merged = [_merged_pr(10)]
    gitclaim.resync_from_github(_home, ["o/a"], fetch_json=_gh(merged=merged))
    (u,) = _uats(_home)
    assert u.get("repo_uat") is True
    u["offered_to"] = "marchhare-26248"
    u["offered_ts"] = _now_iso(30)
    u["offered_channel"] = "#marchhare"
    gitclaim._write_queue(
        gitclaim.queue_path(_home),
        {"v": 1, "unaccepted": [u], "accepted": []},
    )
    blocking = {
        "number": 2970,
        "title": "Harvest re-promotes FAIL-supersede process lessons into harvest (twin MRB loop)",
        "labels": [{"name": "feature-request"}, {"name": "via-intake"}],
        "state": "open",
    }
    gitclaim.resync_from_github(
        _home, ["o/a"], fetch_json=_gh(issues=[blocking], merged=merged)
    )
    assert _uats(_home) == []
