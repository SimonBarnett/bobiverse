"""FR #4963: intake dedupe_key comments / reopens instead of twin issues."""
from __future__ import annotations

import json
from pathlib import Path

import intake


REPO = "SimonBarnett/bobiverse"
REPO2 = "SimonBarnett/a-search"


def _payload(
    *,
    title: str = "import failure: awin merge",
    body: str = "merge threw",
    idem: str,
    dedupe: str = "awin|feed-1|E_MERGE",
    repo: str = REPO,
    kind: str = "issue",
) -> dict:
    return {
        "kind": kind,
        "repo": repo,
        "title": title,
        "body": body,
        "idempotency_key": idem,
        "dedupe_key": dedupe,
    }


def _process(home: Path, payload: dict, filer: intake.FakeGitHubFiler) -> intake.IntakeResult:
    return intake.process_intake(
        home,
        payload,
        filer=filer,
        rate=intake.RateLimiter(per_min=60),
        client_ip="127.0.0.1",
    )


def test_validate_bad_dedupe_key_over_128():
    err, _ = intake.validate_payload(
        {
            "repo": REPO,
            "title": "t",
            "body": "b",
            "dedupe_key": "x" * 129,
        }
    )
    assert err == "bad_dedupe_key"
    assert "bad_dedupe_key" in intake.PERMANENT_INTAKE_ERRORS


def test_open_match_comments_no_new_issue(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(tmp_path, _payload(idem="run-a"), filer)
    assert r1.status == 202
    assert r1.body.get("action") == "filed"
    assert r1.body.get("number")
    n = r1.body["number"]
    assert len(filer.issues) == 1
    marker = intake.intake_dedupe_marker(REPO, "awin|feed-1|E_MERGE")
    assert marker in (filer.issues[0].get("body") or "")

    r2 = _process(
        tmp_path,
        _payload(idem="run-b", title="import failure again", body="same merge"),
        filer,
    )
    assert r2.body.get("action") == "commented"
    assert r2.body.get("number") == n
    assert r2.body.get("url") == r1.body.get("url")
    assert len(filer.issues) == 1
    assert len(filer.comments) == 1
    assert "import failure again" in filer.comments[0]["body"]
    assert "same merge" in filer.comments[0]["body"]


def test_closed_match_reopens_and_comments(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(tmp_path, _payload(idem="c1"), filer)
    n = r1.body["number"]
    filer.issues[0]["state"] = "closed"

    r2 = _process(tmp_path, _payload(idem="c2", title="it failed again", body="back"), filer)
    assert r2.body.get("action") == "reopened"
    assert r2.body.get("number") == n
    assert filer.issues[0]["state"] == "open"
    assert len(filer.comments) == 1
    assert "it failed again" in filer.comments[0]["body"]


def test_no_match_files_with_marker_and_index(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r = _process(tmp_path, _payload(idem="n1"), filer)
    assert r.body.get("action") == "filed"
    sha = intake.intake_dedupe_sha(REPO, "awin|feed-1|E_MERGE")
    idx = tmp_path / "intake" / "records" / f"dedupe-{sha[:32]}.json"
    assert idx.is_file()
    meta = json.loads(idx.read_text(encoding="utf-8"))
    assert meta["repo"] == REPO
    assert meta["number"] == r.body["number"]
    assert meta["url"] == r.body["url"]
    assert meta["intake_id"] == r.body["intake_id"]


def test_idempotent_retry_no_second_comment(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    _process(tmp_path, _payload(idem="same-post"), filer)
    _process(tmp_path, _payload(idem="later", title="again"), filer)
    assert len(filer.comments) == 1
    r3 = _process(tmp_path, _payload(idem="later", title="again"), filer)
    assert r3.body.get("duplicate") is True
    assert r3.body.get("action") == "commented"
    assert r3.body.get("number")
    assert len(filer.comments) == 1
    assert len(filer.issues) == 1


def test_idempotent_retry_reopens_closed_issue_and_comments_once(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    payload = _payload(idem="closed-repeat")
    first = _process(tmp_path, payload, filer)
    number = first.body["number"]
    filer.issues[0]["state"] = "closed"

    retried = _process(tmp_path, payload, filer)
    assert retried.body.get("duplicate") is True
    assert retried.body.get("action") == "reopened"
    assert filer.issues[0]["state"] == "open"
    assert len(filer.comments) == 1

    _process(tmp_path, payload, filer)
    assert filer.issues[0]["number"] == number
    assert len(filer.comments) == 1
    assert len(filer.issues) == 1


def test_lost_index_rebuilds_from_marker_search(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(tmp_path, _payload(idem="lost-1"), filer)
    sha = intake.intake_dedupe_sha(REPO, "awin|feed-1|E_MERGE")
    idx = tmp_path / "intake" / "records" / f"dedupe-{sha[:32]}.json"
    idx.unlink()
    r2 = _process(tmp_path, _payload(idem="lost-2", title="replay"), filer)
    assert r2.body.get("action") == "commented"
    assert r2.body.get("number") == r1.body["number"]
    assert len(filer.issues) == 1
    assert idx.is_file()


def test_same_dedupe_two_repos_two_issues(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(tmp_path, _payload(idem="r1", repo=REPO), filer)
    r2 = _process(tmp_path, _payload(idem="r2", repo=REPO2), filer)
    assert r1.body.get("action") == "filed"
    assert r2.body.get("action") == "filed"
    assert r1.body.get("number") != r2.body.get("number")
    assert len(filer.issues) == 2


def test_outbox_drain_dedupe_matches_live(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    first = _process(tmp_path, _payload(idem="live-1"), filer)
    n = first.body["number"]

    filer.down = True
    queued = _process(
        tmp_path,
        _payload(idem="drain-1", title="queued fail", body="github down"),
        filer,
    )
    assert queued.body.get("queued") is True
    outbox = tmp_path / "intake" / "outbox"
    rows = list(outbox.glob("*.json"))
    assert rows
    raw = json.loads(rows[0].read_text(encoding="utf-8"))
    assert raw["norm"].get("dedupe_key") == "awin|feed-1|E_MERGE"

    filer.down = False
    stats = intake.drain_intake_outbox(tmp_path, filer)
    assert first.body["intake_id"] not in stats.deferred
    assert len(filer.issues) == 1
    assert filer.issues[0]["number"] == n
    assert len(filer.comments) == 1
    assert "queued fail" in filer.comments[0]["body"]

    stats2 = intake.drain_intake_outbox(tmp_path, filer)
    assert stats2.filed == []
    assert len(filer.comments) == 1
