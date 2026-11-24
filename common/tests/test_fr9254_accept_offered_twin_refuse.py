# -*- coding: utf-8 -*-
"""FR #9254: chair accept_offered must refuse twin accept for the same nick.

When a seat already has an accepted row, a second ACK must not stamp another
accepted row. Clear offered_to on the twin offered row so another seat can take it.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(tmp_path, {"ionos", "redqueen"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "url": kw.pop("url", f"https://github.com/{repo}/issues/{num}"),
    }
    r.update(kw)
    return r


def _queue(home: Path, unaccepted: list, accepted: list | None = None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": unaccepted,
            "accepted": list(accepted or []),
            "done": [],
        },
    )


def test_accept_offered_refuses_when_nick_already_accepted(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    nick = "redqueen-6148"
    already = _row(
        "SimonBarnett/bobiverse",
        "FIX",
        9093,
        1,
        nick=nick,
        accepted_ts="2026-11-23T05:54:51Z",
        url="https://github.com/SimonBarnett/bobiverse/pull/9093",
    )
    twin_offer = _row(
        "SimonBarnett/bobiverse",
        "FR",
        9236,
        2,
        offered_to=nick,
        offered_channel="#redqueen",
        offered_ts="2026-11-23T05:53:00Z",
    )
    _queue(home, [twin_offer], accepted=[already])

    st, job = gitclaim.accept_offered(home, nick, "#redqueen")
    assert st == "twin", f"expected twin refuse, got {st!r}"
    assert isinstance(job, dict) and str(job.get("id") or "") in ("#9093", "9093")

    doc = gitclaim.load_queue(home)
    accepted_nicks = [
        str(r.get("nick") or "").lower()
        for r in doc.get("accepted") or []
        if isinstance(r, dict)
    ]
    assert accepted_nicks.count(nick.lower()) == 1
    ids = [str(r.get("id") or "") for r in doc.get("accepted") or []]
    assert "#9236" not in ids and "9236" not in {i.lstrip("#") for i in ids}

    # Twin offer cleared so another seat can take it (not stuck on this nick).
    unacc = doc.get("unaccepted") or []
    twin_rows = [r for r in unacc if str(r.get("id") or "") in ("#9236", "9236")]
    assert twin_rows, "twin row must stay unaccepted"
    assert not str(twin_rows[0].get("offered_to") or "").strip()


def test_accept_offered_same_job_still_ok_when_empty_accepted(tmp_path, monkeypatch):
    """Happy path unchanged: first accept still moves offered → accepted."""
    home = _home(tmp_path, monkeypatch)
    nick = "redqueen-1"
    offer = _row(
        "SimonBarnett/bobiverse",
        "FR",
        9236,
        1,
        offered_to=nick,
        offered_channel="#redqueen",
        offered_ts="2026-11-23T05:53:00Z",
    )
    _queue(home, [offer], accepted=[])
    st, job = gitclaim.accept_offered(home, nick, "#redqueen")
    assert st == "ok"
    assert job and str(job.get("id") or "") in ("#9236", "9236")
    doc = gitclaim.load_queue(home)
    assert len(doc.get("accepted") or []) == 1
    assert not doc.get("unaccepted")
