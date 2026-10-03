"""FR #180: skip skill/harvest/safe-to-close FRs; GIVEUP/NACK cooldown; prune junk rows."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import gitclaim
import shop_listen


def _issue_payload(num: int, *, title: str, body: str = "", labels=None, state: str = "open"):
    labs = []
    for name in labels or []:
        labs.append({"name": name})
    return {
        "action": "opened",
        "repository": {"full_name": "SimonBarnett/bobiverse"},
        "issue": {
            "number": num,
            "title": title,
            "body": body,
            "state": state,
            "labels": labs,
        },
    }


def test_skill_and_harvest_issues_do_not_become_fr_claims():
    skill = gitclaim.claim_from_payload("issues", _issue_payload(10, title="harvest: lesson", labels=["skill", "via-intake"]))
    assert skill is None
    harvest_title = gitclaim.claim_from_payload("issues", _issue_payload(11, title="harvest: NACK umbrella"))
    assert harvest_title is None
    plain = gitclaim.claim_from_payload("issues", _issue_payload(12, title="FR: real work", labels=["feature-request"]))
    assert plain is not None and plain.task == "FR" and plain.id == "#12"


def test_safe_to_close_and_closed_issues_do_not_enqueue():
    safe = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(20, title="smoke", body="Issue #20 closed as Safe to close smoke"),
    )
    assert safe is None
    closed = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(21, title="already done", state="closed"),
    )
    assert closed is None


def test_umbrella_label_skips_fr_enqueue():
    um = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(73, title="FR: airc umbrella", labels=["umbrella", "feature-request"]),
    )
    assert um is None


def test_apply_queue_skips_unassignable_and_stores_title(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # PR #1236: needs-mrb1 is enqueueable (vision cue); still not require_machine=mrb1.
    claim_mrb1 = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(30, title="FR: ship it", labels=["feature-request", "needs-mrb1"]),
    )
    assert claim_mrb1 is not None
    assert "needs-mrb1" in claim_mrb1.labels
    claim = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(31, title="FR: ship it", labels=["feature-request"]),
    )
    assert claim is not None
    assert gitclaim.apply_queue_event(tmp_path, claim) == "added"
    rows = gitclaim.load_unaccepted(tmp_path)
    assert len(rows) == 1
    assert rows[0]["title"] == "FR: ship it"
    assert "feature-request" in rows[0]["labels"]

    junk = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#99",
        event="issues",
        action="opened",
        line="",
        title="harvest: junk",
        labels=("skill",),
    )
    assert gitclaim.apply_queue_event(tmp_path, junk) == "noop"
    assert len(gitclaim.load_unaccepted(tmp_path)) == 1


def test_giveup_sets_cooldown_and_offer_skips_until_expired(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#118",
                    "nick": "marchhare-1",
                    "seq": 1,
                    "ts": "2026-10-02T12:00:00Z",
                    "line": "x",
                }
            ],
        },
    )
    t0 = time.time()
    st, job = shop_listen.return_job_to_unaccepted(
        tmp_path, repo="SimonBarnett/bobiverse", task="FR", ident="#118", now=t0
    )
    assert st == "ok" and job is not None
    assert job.get("cooldown_until")
    assert int(job.get("giveup_count") or 0) == 1
    assert not job.get("needs_human")

    # FR #1080 / #1122: cooldown is per giveup seat — other seats may take the row immediately.
    st_giver, offered_giver = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare", now=t0 + 10)
    assert st_giver == "empty" and offered_giver is None

    st2, offered = gitclaim.offer_focus_top(tmp_path, "marchhare-2", "#marchhare", now=t0 + 10)
    assert st2 == "ok" and offered["id"] == "#118"


def test_second_giveup_marks_needs_human(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    row = {
        "repo": "o/r",
        "task": "FR",
        "id": "#1",
        "nick": "a-1",
        "seq": 1,
        "ts": "2026-10-02T12:00:00Z",
        "line": "x",
        "giveup_count": 1,
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": [], "accepted": [row]})
    st, job = shop_listen.return_job_to_unaccepted(tmp_path, repo="o/r", task="FR", ident="#1", now=time.time())
    assert st == "ok"
    assert job.get("needs_human") is True
    # PR #1236: with giveup_seats set, only those seats are blocked — other seats may take it.
    seats = str(job.get("giveup_seats") or "")
    if seats.strip():
        assert gitclaim.offer_focus_top(tmp_path, "a-1", "#a", now=time.time() + 10_000)[0] == "empty"
        assert gitclaim.offer_focus_top(tmp_path, "b-2", "#b", now=time.time() + 10_000)[0] == "ok"
    else:
        # Bare needs_human with no giveup_seats remains a global gate.
        assert gitclaim.offer_focus_top(tmp_path, "b-2", "#b", now=time.time() + 10_000)[0] == "empty"


def test_prune_drops_skill_and_safe_to_close_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rows = [
        {"repo": "o/r", "task": "FR", "id": "#1", "seq": 1, "ts": "t", "line": "x", "title": "FR: keep"},
        {
            "repo": "o/r",
            "task": "FR",
            "id": "#2",
            "seq": 2,
            "ts": "t",
            "line": "x",
            "title": "harvest: lesson",
            "labels": ["skill"],
        },
        {
            "repo": "o/r",
            "task": "FR",
            "id": "#3",
            "seq": 3,
            "ts": "t",
            "line": "x",
            "title": "smoke",
            "body": "Safe to close",
        },
    ]
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": rows, "accepted": []})
    res = gitclaim.prune_unassignable_queue(tmp_path)
    assert res["ok"] and res["dropped"] == 2
    left = gitclaim.load_unaccepted(tmp_path)
    assert [r["id"] for r in left] == ["#1"]


def test_resync_does_not_readd_skill_or_safe_to_close(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": [], "accepted": []})

    def fetch(url):
        if "/issues?" in url:
            return [
                {"number": 1, "title": "FR: real", "body": "", "labels": [{"name": "feature-request"}]},
                {"number": 2, "title": "harvest: x", "body": "", "labels": [{"name": "skill"}]},
                {"number": 3, "title": "smoke", "body": "Safe to close stub", "labels": []},
            ]
        if "/pulls?" in url:
            return []
        return []

    res = gitclaim.resync_from_github(tmp_path, ["o/a"], fetch_json=fetch)
    assert res["ok"]
    ids = [r["id"] for r in gitclaim.load_unaccepted(tmp_path)]
    assert ids == ["#1"]


def test_mrb_home_label_and_handoff_title_do_not_become_fr_claims():
    """bobiverse#258: evergreen MRB-home boards must not enqueue as FR."""
    labeled = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(
            3,
            title="MRB: agentic_fomprep origin/main (Cursor/Grok handoff)",
            labels=["feature-request", "mrb-home", "mrb-pass"],
        ),
    )
    assert labeled is None
    title_only = gitclaim.claim_from_payload(
        "issues",
        _issue_payload(
            4,
            title="Hostile MRB home for HEAD of this repo",
            labels=["feature-request"],
        ),
    )
    assert title_only is None
    assert gitclaim.issue_skip_fr_reason(title="x", labels=("mrb-home",)) == "label:mrb-home"
    assert (
        gitclaim.issue_skip_fr_reason(
            title="MRB: agentic_fomprep origin/main (Cursor/Grok handoff)"
        )
        == "evergreen_mrb_home"
    )


def test_offer_focus_skips_mrb_home_row_even_when_only_line_set(tmp_path, monkeypatch):
    """Stale queue rows with labels/line but empty title must still be skipped at offer."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#3",
                    "seq": 1,
                    "ts": "t",
                    "line": "MRB: agentic_fomprep origin/main (Cursor/Grok handoff)",
                    "labels": ["mrb-home", "feature-request"],
                    # title intentionally missing (legacy row shape)
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#258",
                    "seq": 2,
                    "ts": "t",
                    "line": "FR: real",
                    "title": "FR: real",
                    "labels": ["feature-request"],
                },
            ],
            "accepted": [],
        },
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#258"
    assert "agentic_fomprep" not in str(job.get("repo") or "")


def test_prune_drops_mrb_home_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rows = [
        {
            "repo": "o/r",
            "task": "FR",
            "id": "#1",
            "seq": 1,
            "ts": "t",
            "line": "keep",
            "title": "FR: keep",
        },
        {
            "repo": "o/r",
            "task": "FR",
            "id": "#3",
            "seq": 2,
            "ts": "t",
            "line": "MRB: x handoff",
            "labels": ["mrb-home"],
        },
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": rows, "accepted": []}
    )
    res = gitclaim.prune_unassignable_queue(tmp_path)
    assert res["ok"] and res["dropped"] == 1
    assert [r["id"] for r in gitclaim.load_unaccepted(tmp_path)] == ["#1"]


def test_coerce_preserves_cooldown_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    row = {
        "repo": "o/r",
        "task": "FR",
        "id": "#7",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "title": "FR: x",
        "labels": ["feature-request"],
        "cooldown_until": "2099-01-01T00:00:00Z",
        "giveup_count": 2,
        "needs_human": True,
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": [row], "accepted": []})
    loaded = gitclaim.load_unaccepted(tmp_path)[0]
    assert loaded["cooldown_until"].startswith("2099")
    assert loaded["giveup_count"] == 2
    assert loaded["needs_human"] is True
    assert loaded["title"] == "FR: x"
