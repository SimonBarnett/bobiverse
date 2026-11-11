"""FR #6595: release_duplicate_done_hold must not prune a newer-head MRB re-review."""
from __future__ import annotations

import gitclaim

SHA = "a" * 40
NEWER = "b" * 40
REPO = "SimonBarnett/a-search"
NICK = "flamingo-30252"


def _write(tmp_path, *, done_sha: str = "", una_sha: str = "", una: bool = True):
    done = [
        {
            "repo": REPO,
            "task": "MRB",
            "id": "#3246",
            "result": "PASS",
            "url": f"https://github.com/{REPO}/pull/3246",
            "done_by": NICK,
            "nick": NICK,
            "pass_sha": done_sha,
        }
    ]
    una_rows = []
    if una:
        row = {
            "repo": REPO,
            "task": "MRB",
            "id": "#3246",
            "seq": 1,
            "ts": "t",
            "line": "",
            "url": f"https://github.com/{REPO}/pull/3246",
        }
        if una_sha:
            row["head_sha"] = una_sha
        una_rows.append(row)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": una_rows, "accepted": [], "done": done},
    )


def test_fr6595_newer_head_unaccepted_survives_hold_release(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        "mrb_merge_gate.fetch_issue_comments",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _write(tmp_path, done_sha=SHA, una_sha=NEWER, una=True)
    assert gitclaim.note_seat_hold(
        tmp_path,
        NICK,
        {"repo": REPO, "task": "MRB", "id": "#3246"},
        via="offer",
    )
    freed = gitclaim.release_duplicate_done_hold(tmp_path, NICK)
    assert "MRB" in freed
    rows = gitclaim.load_unaccepted(tmp_path)
    match = [r for r in rows if r.get("id") == "#3246"]
    assert len(match) == 1
    assert match[0].get("head_sha") == NEWER
    assert gitclaim.seat_open_job(tmp_path, NICK) == ""


def test_fr6595_same_sha_still_prunes(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        "mrb_merge_gate.fetch_issue_comments",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _write(tmp_path, done_sha=SHA, una_sha=SHA, una=True)
    assert gitclaim.note_seat_hold(
        tmp_path,
        NICK,
        {"repo": REPO, "task": "MRB", "id": "#3246"},
        via="offer",
    )
    freed = gitclaim.release_duplicate_done_hold(tmp_path, NICK)
    assert "MRB" in freed
    rows = gitclaim.load_unaccepted(tmp_path)
    assert [r for r in rows if r.get("id") == "#3246"] == []


def test_fr6595_missing_sha_still_prunes_offline_phantom(tmp_path, monkeypatch):
    """FR #6565: no SHAs => prune phantom (offline done[] PASS clear)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(
        "mrb_merge_gate.fetch_issue_comments",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    _write(tmp_path, done_sha="", una_sha="", una=True)
    assert gitclaim.note_seat_hold(
        tmp_path,
        NICK,
        {"repo": REPO, "task": "MRB", "id": "#3246"},
        via="offer",
    )
    freed = gitclaim.release_duplicate_done_hold(tmp_path, NICK)
    assert "MRB" in freed
    assert [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("id") == "#3246"] == []


def test_fr6595_source_pins():
    src = open(gitclaim.__file__, encoding="utf-8").read()
    assert "6595" in src
    assert "release_duplicate_done_hold" in src
