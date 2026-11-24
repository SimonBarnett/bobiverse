# -*- coding: utf-8 -*-
"""FR #9602: all-gave-up stall fingerprint keys owner/repo (not #N)."""
from __future__ import annotations

from pathlib import Path

import stall_detectors as sd
import stall_filer as sf


def _abandoned_fr(repo: str, num: int, giveups: list[str]) -> dict:
    return {
        "task": "FR",
        "repo": repo,
        "id": f"#{num}",
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": f"FR {num}",
        "giveup_seats": ",".join(giveups),
        "giveup_count": len(giveups),
    }


def test_fr9602_stable_key_strips_issue_number():
    row = _abandoned_fr("SimonBarnett/bobiverse", 8722, ["flamingo-1"])
    assert sd._all_gave_up_stable_key(row) == "SimonBarnett/bobiverse"
    assert sd.fingerprint(sd.ALL_GAVE_UP_ID, sd._all_gave_up_stable_key(row)) == (
        "stall:all-gave-up:SimonBarnett/bobiverse"
    )


def test_fr9602_two_rows_same_repo_share_fingerprint():
    live = {"flamingo-1", "marchhare-1"}
    giveups = ["flamingo-1", "marchhare-1"]
    snap = {
        "live": live,
        "unaccepted": [
            _abandoned_fr("SimonBarnett/bobiverse", 8722, giveups),
            _abandoned_fr("SimonBarnett/bobiverse", 8997, giveups),
        ],
    }
    found = sd.detect_all_gave_up(snap)
    assert len(found) == 2
    fps = {sd.fingerprint(f["id"], f["key"]) for f in found}
    assert fps == {"stall:all-gave-up:SimonBarnett/bobiverse"}
    rows = {f["evidence"]["row"] for f in found}
    assert rows == {
        "SimonBarnett/bobiverse#8722",
        "SimonBarnett/bobiverse#8997",
    }
    assert all(f["key"] == "SimonBarnett/bobiverse" for f in found)
    assert all(f["title"] == "stall:all-gave-up:SimonBarnett/bobiverse" for f in found)


def test_fr9602_different_repos_remain_distinct():
    live = {"flamingo-1"}
    snap = {
        "live": live,
        "unaccepted": [
            _abandoned_fr("SimonBarnett/bobiverse", 1, ["flamingo-1"]),
            _abandoned_fr("SimonBarnett/skills-visionary", 176, ["flamingo-1"]),
        ],
    }
    found = sd.detect_all_gave_up(snap)
    assert {f["key"] for f in found} == {
        "SimonBarnett/bobiverse",
        "SimonBarnett/skills-visionary",
    }


def test_fr9602_filer_second_row_comments_same_issue(tmp_path: Path):
    """Two bobiverse row ids in one scan -> one create + one comment."""
    live = {"flamingo-1", "marchhare-1"}
    giveups = ["flamingo-1", "marchhare-1"]
    findings = sd.detect_all(
        {
            "live": live,
            "unaccepted": [
                _abandoned_fr("SimonBarnett/bobiverse", 8722, giveups),
                _abandoned_fr("SimonBarnett/bobiverse", 8997, giveups),
            ],
            "accepted": [],
            "idle": set(),
            "last_bored": {},
        }
    )
    agu = [f for f in findings if f["id"] == sd.ALL_GAVE_UP_ID]
    assert len(agu) == 2
    assert agu[0]["fingerprint"] == agu[1]["fingerprint"] == (
        "stall:all-gave-up:SimonBarnett/bobiverse"
    )

    created: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []

    def create(title: str, body: str):
        created.append((title, body))
        assert title == "stall:all-gave-up:SimonBarnett/bobiverse"
        assert "bobiverse#8722" in body or "bobiverse#8997" in body
        return {"number": 9602}

    def list_open(fp: str):
        return [{"number": 9602, "title": fp}] if created else []

    def comment(n: int, body: str):
        comments.append((n, body))
        assert n == 9602
        assert "bobiverse#" in body

    actions = sf.apply_findings(
        agu,
        home=tmp_path,
        now=1_700_000_000.0,
        list_open=list_open,
        create=create,
        comment=comment,
        cooldown_s=0,
        comment_s=0,
    )
    kinds = [a.get("action") for a in actions]
    assert kinds.count("created") == 1
    assert kinds.count("comment") == 1
    assert len(created) == 1
    assert len(comments) == 1
    # Both parent rows appear across create body + comment body.
    blob = created[0][1] + comments[0][1]
    assert "bobiverse#8722" in blob
    assert "bobiverse#8997" in blob


def test_fr9602_stamp_still_parks_specific_row(tmp_path: Path):
    import gitclaim

    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8997",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/8997",
        "title": "winrm",
        "giveup_seats": "flamingo-1",
        "giveup_count": 1,
        "line": "x",
        "ts": "t",
        "seq": 1,
        "event": "",
        "action": "",
    }
    other = dict(row)
    other["id"] = "#8998"
    other["url"] = "https://github.com/SimonBarnett/bobiverse/issues/8998"
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row, other], "accepted": [], "done": []},
    )
    findings = [
        {
            "id": sd.ALL_GAVE_UP_ID,
            "key": "SimonBarnett/bobiverse",
            "fingerprint": "stall:all-gave-up:SimonBarnett/bobiverse",
            "evidence": {"row": "SimonBarnett/bobiverse#8997", "repo": "SimonBarnett/bobiverse"},
        }
    ]
    n = sd.stamp_needs_human_for_all_gave_up(tmp_path, findings)
    assert n == 1
    q = gitclaim.load_queue(tmp_path)["unaccepted"]
    by_id = {r["id"]: r for r in q}
    assert gitclaim.row_needs_human(by_id["#8997"]) is True
    assert gitclaim.row_needs_human(by_id["#8998"]) is False
