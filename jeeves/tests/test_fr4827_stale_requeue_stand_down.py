"""FR #4827: 45 min is not a re-offer; a later PR from the stale seat stands the duplicate down."""
from __future__ import annotations

import time
from pathlib import Path

import bobreport
import gitclaim

ORIG = "marchhare-18680"
DUP = "flamingo-34008"


def _home(home: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare","flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_bored_at_45_min_does_not_reoffer(tmp_path: Path, monkeypatch):
    _home(tmp_path, monkeypatch)
    now = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2700))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#4428",
                    "nick": ORIG,
                    "accepted_ts": ts,
                    "ts": ts,
                }
            ],
        },
    )
    gitclaim.note_worker_activity(tmp_path, ORIG, now - 10_000)
    assert gitclaim.bored_gate(tmp_path, ORIG, "#marchhare", now) == "busy"
    assert gitclaim.release_stale_busy(tmp_path, ORIG, now) is False
    assert len(gitclaim.load_accepted(tmp_path)) == 1


def test_pr_from_original_prunes_duplicate_and_stands_down(tmp_path: Path, monkeypatch):
    _home(tmp_path, monkeypatch)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#4428",
                    "nick": DUP,
                    "accepted_by": DUP,
                    "accepted_ts": now,
                }
            ],
            "done": [
                {
                    "repo": "SimonBarnett/a-search",
                    "task": "FR",
                    "id": "#4428",
                    "nick": ORIG,
                    "result": "STALE_BUSY",
                    "reconcile": "STALE_BUSY",
                    "done_ts": now,
                }
            ],
        },
    )
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/a-search",
        task="MRB",
        id="4433",
        event="pull_request",
        action="opened",
        line="GIT pull_request opened",
        refs=("#4428",),
        title="fix live worker",
        body="Closes #4428",
    )
    assert gitclaim.apply_queue_event(tmp_path, claim) in ("added", "updated", "duplicate")
    accepted = gitclaim.load_accepted(tmp_path)
    assert not any(
        str(r.get("task") or "").upper() == "FR" and str(r.get("id")) == "#4428" for r in accepted
    )
    notes = gitclaim.drain_stand_down(tmp_path)
    assert len(notes) == 1
    assert notes[0]["nick"] == DUP
    assert notes[0]["channel"] == "#flamingo"
    assert notes[0]["text"].startswith("stand down FR SimonBarnett/a-search#4428")
    assert ORIG in notes[0]["text"]
    assert "4433" in notes[0]["text"]
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(str(r.get("reconcile") or "") == "DUPLICATE_STALE" and str(r.get("nick")) == DUP for r in done)
