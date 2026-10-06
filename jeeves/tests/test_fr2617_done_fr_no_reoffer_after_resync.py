"""FR #2617: DONE FR + open Closes PR must not re-offer the FR after resync."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import shop_listen


def _seed_live(home, machines: dict[str, list[str]]):
    digest = bobreport.empty_digest()
    for mid, pids in machines.items():
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {
            pid: {"state": "idle", "nick": f"{mid}-{pid}"} for pid in pids
        }
    bobreport.save_digest(home, digest)


def test_fr2617_done_fr_resync_sibling_gets_mrb_not_fr(tmp_path, monkeypatch):
    """DONE FR with PR URL → resync (issue+Closes PR open) → sibling !bored gets MRB only."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None

    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2612",
                    "seq": 1,
                    "nick": "marchhare-9524",
                    "ts": "t",
                    "line": "x",
                    "channel": "#marchhare",
                    "accepted_ts": "t",
                }
            ],
            "done": [],
        },
    )
    st, _ = shop_listen.complete_job_by_ref(
        tmp_path,
        nick="marchhare-9524",
        repo="SimonBarnett/bobiverse",
        task="FR",
        ident="#2612",
        result="PASS",
        url="https://github.com/SimonBarnett/bobiverse/pull/2615",
    )
    assert st == "ok"

    def fetch(url: str):
        if "/issues?" in url:
            return [
                {
                    "number": 2612,
                    "title": "airc long output stall",
                    "body": "x",
                    "labels": [{"name": "via-intake"}],
                    "state": "open",
                }
            ]
        if "/pulls?" in url and "state=open" in url:
            return [
                {
                    "number": 2615,
                    "title": "fix(airc): queue long Command replies",
                    "body": "\ufeffCloses SimonBarnett/bobiverse#2612\n",
                    "draft": False,
                    "html_url": "https://github.com/SimonBarnett/bobiverse/pull/2615",
                }
            ]
        return []

    out = gitclaim.resync_from_github(
        tmp_path, ["SimonBarnett/bobiverse"], fetch_json=fetch
    )
    assert out.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r.get("task") == "FR" and r.get("id") == "#2612" for r in rows)
    assert any(r.get("task") == "MRB" and r.get("id") == "#2615" for r in rows)
    # DONE FR with open implement PR must survive the still-open done[] strip (FR #2617).
    done = gitclaim.load_queue(tmp_path).get("done") or []
    assert any(
        r.get("task") == "FR"
        and r.get("id") == "#2612"
        and "/pull/2615" in str(r.get("url") or "")
        for r in done
    )

    _seed_live(tmp_path, {"marchhare": ["39912", "9524"]})
    st2, job2 = gitclaim.offer_focus_top(tmp_path, "marchhare-39912", "#marchhare")
    assert st2 == "ok"
    assert job2["task"] == "MRB"
    assert job2["id"] == "#2615"


def test_fr2617_done_fr_survives_resync_when_mrb_row_missing(tmp_path, monkeypatch):
    """Even if the MRB unaccepted row is gone, done[]+/pull/ + open PR keeps FR out."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None

    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2612",
                    "nick": "marchhare-9524",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/2615",
                    "done_ts": "t",
                }
            ],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            return [
                {
                    "number": 2612,
                    "title": "stall",
                    "body": "x",
                    "labels": [{"name": "via-intake"}],
                    "state": "open",
                }
            ]
        if "/pulls?" in url and "state=open" in url:
            return [
                {
                    "number": 2615,
                    "title": "fix",
                    "body": "Closes SimonBarnett/bobiverse#2612",
                    "draft": False,
                    "html_url": "https://github.com/SimonBarnett/bobiverse/pull/2615",
                }
            ]
        return []

    gitclaim.resync_from_github(
        tmp_path, ["SimonBarnett/bobiverse"], fetch_json=fetch
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r.get("task") == "FR" and r.get("id") == "#2612" for r in rows)
    assert any(r.get("task") == "MRB" and r.get("id") == "#2615" for r in rows)


def test_fr2617_keeps_2389_reoffer_when_closes_pr_gone(tmp_path, monkeypatch):
    """Open issue whose implement PR vanished must re-queue as FR (FR #2389)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})["simonbarnett/bobiverse#2612"] = gitclaim._utc_now()

    gitclaim._ledger_update(tmp_path, _stamp)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#2612",
                    "nick": "marchhare-9524",
                    "url": "https://github.com/SimonBarnett/bobiverse/pull/2615",
                    "done_ts": "t",
                }
            ],
        },
    )

    def fetch(url: str):
        if "/issues?" in url:
            return [
                {
                    "number": 2612,
                    "title": "stall",
                    "body": "x",
                    "labels": [{"name": "via-intake"}],
                    "state": "open",
                }
            ]
        return []

    gitclaim.resync_from_github(
        tmp_path, ["SimonBarnett/bobiverse"], fetch_json=fetch
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(r.get("task") == "FR" and r.get("id") == "#2612" for r in rows)
    assert not any(r.get("task") == "MRB" for r in rows)
    # Premature/stale DONE stripped once implement PR is gone.
    assert not any(
        r.get("id") == "#2612" for r in (gitclaim.load_queue(tmp_path).get("done") or [])
    )
