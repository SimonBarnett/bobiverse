"""FR #4906: conflict FIX DONE with no push must re-offer on resync; !assign FIX accepts DIRTY+green."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SCRIPTS = ROOT / "common" / "scripts"
if str(COMMON_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS))

mrb_merge_on_green = importlib.import_module("mrb_merge_on_green")
gitclaim = importlib.import_module("gitclaim")
bobreport = importlib.import_module("bobreport")

SHA = "f" * 40
REPO = "SimonBarnett/a-search"
PR = "4631"
NICK = "flamingo-6652"


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def _finish_fix(home: Path, nick: str = NICK) -> None:
    q = gitclaim.load_queue(home)
    done = []
    for row in q.get("unaccepted") or []:
        if str(row.get("task") or "").upper() != "FIX":
            continue
        row["nick"] = nick
        row["done_by"] = nick
        row["result"] = "DONE"
        done.append(row)
    for row in q.get("accepted") or []:
        if str(row.get("task") or "").upper() != "FIX":
            continue
        row["nick"] = nick
        row["done_by"] = nick
        row["result"] = "DONE"
        done.append(row)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": done},
    )


def _fix_rows(home: Path) -> list[dict]:
    q = gitclaim.load_queue(home)
    return [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
    ]


def _register(home: Path, monkeypatch, nick: str = "marchhare-23068") -> None:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": "",
        "worker_list": [{"nick": nick, "state": "idle", "work": ""}],
        "workers": {"23068": {"pid": "23068", "nick": nick, "state": "idle"}},
    }
    bobreport.save_digest(home, doc)


def test_conflict_fix_done_same_sha_resync_reoffers(tmp_path: Path):
    """DONE conflict FIX + unchanged SHA + conflict_blocked -> one fresh FIX on resync."""
    home = _home(tmp_path)
    url = f"https://github.com/{REPO}/pull/{PR}"
    assert (
        mrb_merge_on_green.enqueue_conflict_fix(
            home, repo=REPO, pr=PR, pass_sha=SHA, url=url, reason="http-405"
        )
        == "added"
    )
    assert len(_fix_rows(home)) == 1
    # Simulate merge-on-green park after HTTP 405.
    doc = mrb_merge_on_green.load_ledger(home)
    mrb_merge_on_green.park_conflict(
        doc,
        {"repo": REPO, "pr": PR, "pass_sha": SHA, "url": url, "nick": ""},
        reason="http-405",
        head_sha=SHA,
    )
    mrb_merge_on_green.save_ledger(home, doc)
    _finish_fix(home)
    assert _fix_rows(home) == []
    # Bare enqueue still dedupes (signature retained) — offer_dirty path must recover.
    assert (
        mrb_merge_on_green.enqueue_conflict_fix(
            home, repo=REPO, pr=PR, pass_sha=SHA, url=url, reason="conflicting"
        )
        == "duplicate"
    )
    pr = {
        "number": int(PR),
        "title": "docs tip",
        "body": f"Closes {REPO}#4623",
        "html_url": url,
        "state": "open",
        "draft": False,
        "auto_merge": {"merge_method": "merge"},
        "head": {"sha": SHA},
        "user": {"login": "u"},
        "checks": "success",
        "mergeable": "CONFLICTING",
        "mergeable_state": "DIRTY",
    }

    def fetch_json(url_s: str):
        if "/pulls/" in url_s and "state=" not in url_s:
            return pr
        if "/pulls" in url_s and "state=closed" not in url_s:
            return [pr]
        if "/issues" in url_s:
            return []
        return []

    gitclaim.resync_from_github(home, [REPO], fetch_json=fetch_json)
    live = _fix_rows(home)
    assert len(live) == 1
    blob = str(live[0].get("body") or "") + " " + str(live[0].get("title") or "")
    assert "conflict" in blob.lower()
    assert SHA[:12] in blob or SHA in str(live[0].get("pass_sha") or "")


def test_assign_fix_accepts_dirty_pr_with_green_checks(tmp_path: Path, monkeypatch):
    home = _home(tmp_path)
    nick = "marchhare-23068"
    _register(home, monkeypatch, nick=nick)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {nick})
    monkeypatch.setattr(gitclaim, "free_seat_nicks", lambda h, live: {nick})
    monkeypatch.setattr(gitclaim, "seat_open_job", lambda *a, **k: "")

    def fake_issue(repo, num):
        return {
            "number": int(PR),
            "state": "open",
            "draft": False,
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "pull_request": {},
            "labels": [],
        }

    def fake_pr(repo, num):
        return {
            "sha": SHA,
            "checks": "success",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
        }

    st, job = gitclaim.assign_row(
        home,
        nick,
        REPO,
        "FIX",
        f"#{PR}",
        fetch_issue=fake_issue,
        fetch_pr=fake_pr,
    )
    assert st == "ok", job
    assert isinstance(job, dict)
    assert str(job.get("task")).upper() == "FIX"
    blob = str(job.get("body") or "") + " " + str(job.get("title") or "")
    assert "conflict" in blob.lower()
