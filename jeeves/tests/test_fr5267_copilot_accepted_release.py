"""FR #5267: copilot-held accepted rows must not sit forever.

Closed issues leave ``accepted`` on the next resync. With Copilot dispatch
off (allowance file absent, or ``enabled: false``), stranded nick=copilot
rows return to the seat queue with give-up semantics. An open Copilot PR
stays on the PR webhook row and is not duplicated.
"""
from __future__ import annotations

import json

import chair_health as ch
import copilot_dispatch as cd
import gitclaim


REPO = "SimonBarnett/bobiverse"


class _Clock:
    def __init__(self) -> None:
        self.t = 1_700_000_000.0

    def __call__(self) -> float:
        return self.t


def _queue(home, accepted, unaccepted=None) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted),
            "done": [],
            "workers": {},
        },
    )


def _fr(num, **extra):
    row = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"issue {num}",
        "state": "open",
        "line": f"FR {REPO}#{num}",
    }
    row.update(extra)
    return row


def _chair(home, clock, *, fetch=None, token=("", "none")):
    logs: list[str] = []
    calls: list[str] = []

    def fetch_json(url, force_refresh=False):
        calls.append(str(url))
        if fetch is not None:
            return fetch(url)
        return []

    j = ch.ChairJobs(
        home,
        home,
        log=logs.append,
        announce=logs.append,
        spawn=False,
        token_loader=lambda: token,
        fetch_json=fetch_json,
        clock=clock,
        sleep=lambda _s: None,
        owners={"SimonBarnett"},
    )
    far = clock.t + 1e9
    j.next_probe = far
    j.next_resync = far
    j.next_merge_on_green = far
    j.next_stall = far
    j.next_webhook_ensure = far
    j.next_intake_outbox = far
    j.next_copilot = far

    def _github_json(method, url, body=None):
        calls.append(str(url))
        raise AssertionError(f"Copilot API must not be called: {method} {url}")

    j._github_json = _github_json
    return j, logs, calls


def _ids(rows, task=None):
    out = []
    for r in rows or []:
        if task and str(r.get("task") or "").upper() != task:
            continue
        out.append(str(r.get("id")))
    return out


def test_closed_issue_copilot_row_dropped_on_resync(tmp_path, monkeypatch):
    """Next resync drops a closed issue from accepted, whoever holds it."""
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", REPO)
    clk = _Clock()
    _queue(
        tmp_path,
        [
            _fr(5240, nick="copilot", accepted_ts="2026-10-30T05:14:14Z"),
            _fr(31, nick="flamingo-9", accepted_ts="2026-10-30T05:14:14Z"),
            _fr(30, nick="flamingo-9", accepted_ts="2026-10-30T05:00:00Z"),
        ],
    )

    def fetch(url):
        if "/issues" in url and "bobiverse" in url and "state=open" in url:
            return [{"number": 30, "title": "still open", "state": "open", "labels": []}]
        return []

    j, logs, calls = _chair(tmp_path, clk, fetch=fetch, token=("local-test", "test"))
    j.next_resync = clk.t
    assert j.tick() is True
    assert j.last_resync.get("ok") is True
    assert not any("copilot_internal" in u for u in calls)

    doc = gitclaim.load_queue(tmp_path)
    assert _ids(doc.get("accepted")) == ["#30"]
    assert "#5240" not in _ids(doc.get("unaccepted"))
    assert "#31" not in _ids(doc.get("unaccepted"))
    done = {
        r.get("id"): r
        for r in (doc.get("done") or [])
        if str(r.get("task") or "").upper() == "FR"
    }
    assert done["#5240"]["result"] == "CLOSED"
    assert str(done["#5240"].get("nick") or "") == ""
    assert done["#31"]["result"] == "CLOSED"
    assert any("github-resync ok" in ln for ln in logs)


def test_disabled_allowance_releases_copilot_rows_to_seats(tmp_path, monkeypatch):
    """Absent allowance, or enabled=false, gives the row back to an IRC seat."""
    monkeypatch.delenv("BOB_FUEL_COPILOT", raising=False)

    def _run(home, allowance):
        clk = _Clock()
        _queue(
            home,
            [
                _fr(12, nick="copilot", accepted_ts="2026-10-30T06:00:00Z"),
                _fr(
                    13,
                    nick="flamingo-2",
                    state="open",
                    cancel_pending=True,
                    cancel_notified=True,
                ),
            ],
        )
        if allowance is not None:
            (home / cd.ALLOWANCE_NAME).write_text(
                json.dumps(allowance) + "\n", encoding="utf-8"
            )
        j, _logs, calls = _chair(home, clk, token=("local-test", "test"))
        j.next_copilot = clk.t
        assert j.tick() is True
        assert calls == []
        assert cd.dispatch_enabled(home) is False
        doc = gitclaim.load_queue(home)
        assert _ids(doc.get("accepted")) == []
        released = [r for r in doc.get("unaccepted") or [] if r.get("id") == "#12"]
        assert len(released) == 1
        assert "copilot" in str(released[0].get("giveup_seats") or "").lower()
        assert released[0].get("cooldown_until")
        assert str(released[0].get("nick") or "") == ""
        assert cd.should_dispatch(released[0], allowance=True) is False
        assert gitclaim.row_gave_up_by(released[0], "copilot") is True
        assert gitclaim.row_on_cooldown(released[0], clk.t, "marchhare-22372") is False
        flags = [r for r in (doc.get("done") or []) if r.get("id") == "#13"]
        assert len(flags) == 1 and flags[0]["result"] == "CLOSED"
        assert "#13" not in _ids(doc.get("unaccepted"))
        st, job = gitclaim.offer_top(
            home, "marchhare-22372", "#marchhare", now=clk.t
        )
        assert st == "ok" and job is not None and job["id"] == "#12"
        st_c, job_c = gitclaim.offer_top(home, "copilot", "#bobiverse", now=clk.t)
        assert job_c is None or job_c.get("id") != "#12"
        assert st_c in ("empty", "ok")

    _run(tmp_path / "absent", None)
    _run(tmp_path / "off", {"enabled": False, "remaining": 5, "state": "ok"})


def test_no_live_task_releases_and_live_task_stays(tmp_path, monkeypatch):
    """Dispatch on: no CCA task/PR goes back to seats; a live task stays put."""
    monkeypatch.delenv("BOB_FUEL_COPILOT", raising=False)

    def _one(home, *, live: bool):
        clk = _Clock()
        cd.set_allowance(home, remaining=4)
        _queue(home, [_fr(12, nick="copilot")])
        if live:
            (home / cd.JOBS_NAME).write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "repo": REPO,
                                "task": "FR",
                                "id": "#12",
                                "task_id": "task-1",
                                "started": clk.t - 30,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
        j, _logs, calls = _chair(home, clk, token=("", "none"))
        j.next_copilot = clk.t
        assert j.tick() is True
        assert calls == []
        doc = gitclaim.load_queue(home)
        if live:
            assert _ids(doc.get("accepted")) == ["#12"]
            assert doc["accepted"][0].get("nick") == "copilot"
            assert _ids(doc.get("unaccepted"), "FR") == []
        else:
            assert _ids(doc.get("accepted")) == []
            row = next(r for r in doc["unaccepted"] if r.get("id") == "#12")
            assert "copilot" in str(row.get("giveup_seats") or "").lower()
            assert cd.should_dispatch(row, allowance=True) is False

    _one(tmp_path / "idle", live=False)
    _one(tmp_path / "live", live=True)


def test_open_copilot_pr_not_duplicated(tmp_path, monkeypatch):
    """An open Copilot PR is tracked once via the PR row, not re-queued as FR."""
    monkeypatch.delenv("BOB_FUEL_COPILOT", raising=False)
    clk = _Clock()
    pr_url = f"https://github.com/{REPO}/pull/55"
    _queue(
        tmp_path,
        [_fr(10, nick="copilot", accepted_ts="2026-10-30T07:00:00Z")],
        unaccepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#55",
                "url": pr_url,
                "title": "copilot pr",
                "state": "open",
                "author_seat": "copilot",
                "refs": ["#10"],
                "line": f"MRB {REPO}#55",
            }
        ],
    )
    j, _logs, calls = _chair(tmp_path, clk, token=("local-test", "test"))
    j.next_copilot = clk.t
    assert j.tick() is True
    assert calls == []

    def _counts():
        doc = gitclaim.load_queue(tmp_path)
        rows = list(doc.get("unaccepted") or []) + list(doc.get("accepted") or [])
        fr = [r for r in rows if r.get("id") == "#10" and str(r.get("task")).upper() == "FR"]
        mrb = [r for r in rows if r.get("id") == "#55" and str(r.get("task")).upper() == "MRB"]
        done = [
            r
            for r in (doc.get("done") or [])
            if r.get("id") == "#10" and str(r.get("task") or "").upper() == "FR"
        ]
        return fr, mrb, done

    fr, mrb, done = _counts()
    assert fr == []
    assert len(mrb) == 1
    assert mrb[0].get("nick") != "copilot"
    assert len(done) == 1
    assert done[0]["result"] == "COPILOT_PR"
    assert pr_url in str(done[0].get("url") or "")
    clk.t += ch.COPILOT_TICK_S + 1
    j.next_copilot = clk.t
    assert j.tick() is True
    fr2, mrb2, done2 = _counts()
    assert fr2 == []
    assert len(mrb2) == 1
    assert len(done2) == 1
    assert calls == []
