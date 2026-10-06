"""FR #2899: open harvest-lesson MRBs stay offerable across resync + author-seat recycle.

Symptom: lesson PRs #2896/#2897 sat unoffered ~9 min after resync dropped=2 while
idle MarchHare seats heard nothing queued. Self-MRB exclusion remains exact-seat only.
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


REPO = "SimonBarnett/bobiverse"
AUTHOR = "marchhare-35592"
SIBLING = "marchhare-28308"
OTHER = "marchhare-42892"


def _digest_live(home, nicks):
    registered_machines.save_registered(home, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    workers = {}
    for n in nicks:
        pid = str(n).rsplit("-", 1)[-1]
        workers[pid] = {"state": "idle", "nick": n}
    digest["machines"]["marchhare"]["workers"] = workers
    # Prefer worker_list when present (live_seat_nicks).
    digest["worker_list"] = [
        {"nick": n, "machine": "marchhare", "state": "idle"} for n in nicks
    ]
    bobreport.save_digest(home, digest)


def _lesson_row(num=2896, *, author=AUTHOR, offered_to="", offered_ts=""):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "url": f"https://github.com/{REPO}/pull/{num}",
        "title": f"lesson(bobiverse-bob-worker): tip for #{num}",
        "body": (
            "MRB: verify lesson.\n\n"
            "Session summary:\nMRB #2892 PASS\n\n"
            f"_source machine=`marchhare` agent=`Invoke-BobiverseHarvest` seat=`{author}`_\n"
        ),
        "labels": ["via-intake", "harvest-lesson"],
        "author_seat": author,
        "implementer_seat": author,
        "event": "pull_request",
        "action": "opened",
        "line": "MRB",
        "ts": "t",
    }
    if offered_to:
        row["offered_to"] = offered_to
        row["offered_ts"] = offered_ts or "2026-10-06T18:10:00+00:00"
        row["offered_channel"] = "#marchhare"
    return row


def _fetch_open_lesson(num=2896, *, author=AUTHOR):
    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return [
                {
                    "number": num,
                    "title": f"lesson(bobiverse-bob-worker): tip for #{num}",
                    "body": (
                        "MRB: verify.\n\nSession summary:\nx\n\n"
                        f"_source seat=`{author}`_\n"
                    ),
                    "draft": False,
                    "html_url": f"https://github.com/{REPO}/pull/{num}",
                    "labels": [{"name": "via-intake"}, {"name": "harvest-lesson"}],
                }
            ]
        if "/issues?" in url:
            return []
        return []

    return fetch


def test_fr2899_resync_keeps_open_lesson_and_names_drops(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_live(tmp_path, [SIBLING, OTHER])
    doc = {
        "v": 1,
        "unaccepted": [
            _lesson_row(2896),
            _lesson_row(2897, author=AUTHOR),
            # Phantom closed MRB — must drop with a named reason.
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2800",
                "seq": 3,
                "url": f"https://github.com/{REPO}/pull/2800",
                "event": "pull_request",
            },
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)

    stats = gitclaim.resync_from_github(
        tmp_path, [REPO], fetch_json=_fetch_open_lesson(2896)
    )
    assert stats.get("ok") is True
    mrbs = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"]
    ids = {gitclaim._norm_row_id(r.get("id")) for r in mrbs}
    assert "#2896" in ids
    # #2897 not returned by fetch this cycle — open-pull survive only for ids still open.
    # Fetch only listed 2896, so 2897 is not in open_pulls → dropped with detail.
    assert "#2800" not in ids
    detail = " ".join(stats.get("dropped_detail") or [])
    assert "MRB" in detail and "2800" in detail
    assert any("not_in_want" in d or "2800" in d for d in (stats.get("dropped_detail") or []))


def test_fr2899_author_seat_recycle_sibling_gets_offer(tmp_path, monkeypatch):
    """Author nick recycled away; sticky offered_to on dead nick must not block sibling."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_live(tmp_path, [SIBLING, OTHER])  # AUTHOR not live
    doc = {
        "v": 1,
        "unaccepted": [
            _lesson_row(
                2896,
                author=AUTHOR,
                offered_to=AUTHOR,
                offered_ts="2026-10-06T18:24:00+00:00",  # fresh sticky
            )
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)

    # Exact author still blocked if somehow live; recycled author is dead pin → cleared.
    st_auth, _ = gitclaim.offer_focus_top(tmp_path, AUTHOR, "#marchhare")
    assert st_auth == "empty"  # not live / no shop activity path still empty for missing

    st, job = gitclaim.offer_focus_top(tmp_path, SIBLING, "#marchhare")
    assert st == "ok"
    assert gitclaim._norm_row_id(job.get("id")) == "#2896"
    assert job.get("offered_to") == SIBLING


def test_fr2899_resync_then_bored_sibling_not_nothing_queued(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_live(tmp_path, [SIBLING, OTHER])
    doc = {
        "v": 1,
        "unaccepted": [_lesson_row(2896, author=AUTHOR)],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    stats = gitclaim.resync_from_github(
        tmp_path, [REPO], fetch_json=_fetch_open_lesson(2896)
    )
    assert stats.get("ok") is True
    mrbs = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"]
    assert any(gitclaim._norm_row_id(r.get("id")) == "#2896" for r in mrbs)

    st, job = gitclaim.offer_focus_top(tmp_path, SIBLING, "#marchhare")
    assert st == "ok"
    assert "/pull/2896" in str(job.get("url") or "")


def test_fr2899_prune_heals_missing_mrb_url_and_names_drop(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2896",
                "seq": 1,
                # missing url — must heal, not drop
                "title": "lesson(bobiverse-bob-worker): x",
                "labels": ["harvest-lesson"],
                "event": "pull_request",
            },
            {
                # cross-repo pull URL → mrb_row_offerable False (FR #595)
                "repo": REPO,
                "task": "MRB",
                "id": "#1",
                "seq": 2,
                "url": "https://github.com/other/other/pull/1",
                "event": "pull_request",
            },
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    out = gitclaim.prune_unassignable_queue(tmp_path)
    assert out.get("ok") is True
    mrbs = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert "/pull/2896" in str(mrbs[0].get("url") or "")
    detail = out.get("dropped_detail") or []
    assert detail and any("mrb_not_offerable" in d for d in detail)


def test_fr2899_idle_offer_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_live(tmp_path, [SIBLING])
    gitclaim.note_idle_after_empty(tmp_path, SIBLING, "#marchhare")
    doc = {
        "v": 1,
        "unaccepted": [_lesson_row(2896, author=AUTHOR)],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    # Make bored_gate ok: age activity past IDLE_S
    gitclaim.note_worker_activity(tmp_path, SIBLING, 0.0)
    logs: list[str] = []
    sent_lines: list[str] = []

    def say(channel, text):
        sent_lines.append(text)
        return True

    n = gitclaim.offer_to_idle_seats(
        tmp_path, say=say, now=10_000.0, log=logs.append
    )
    assert n == 1
    assert sent_lines and "MRB" in sent_lines[0] and "2896" in sent_lines[0]
    assert logs and "git-claim idle offered" in logs[0] and "2896" in logs[0]
