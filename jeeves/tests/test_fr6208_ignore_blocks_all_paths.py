"""FR #6208: !ignore must block enqueue, offer fallback, ACK/accept, and re-purge."""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import shop_listen
import pytest


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(tmp_path, {"ionos", "redqueen", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-07T10:00:{seq:02d}Z",
        "line": "x",
    }
    if str(task).upper() == "MRB":
        r.setdefault("url", f"https://github.com/{repo}/pull/{num}")
        r.setdefault("event", "pull_request")
        r.setdefault("action", "synchronize")
    r.update(kw)
    return r


def _queue(home, rows, accepted=None):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": list(accepted or [])},
    )


def test_offer_fallback_does_not_leak_ignored_only_queue(_home):
    """When every unaccepted row is ignored, offer_focus_top must stay empty.

    Regression: ordered_unaccepted drops ignored, then non-strict fallback walked
    the raw unaccepted list and re-offered ignored repos (agentic_fomprep after !ignore).
    """
    repo = "SimonBarnett/agentic_fomprep"
    _queue(
        _home,
        [
            _row(repo, "MRB", 322, 1),
            _row(repo, "MRB", 335, 2),
        ],
    )
    assert "purged 2" in fi.handle_ignore_cmd(_home, repo)[0]
    # Simulate late synchronize re-enqueue that ignored the ignore list.
    _queue(
        _home,
        [
            _row(repo, "MRB", 322, 1),
            _row(repo, "MRB", 335, 2),
        ],
    )
    st, job = gitclaim.offer_focus_top(_home, "redqueen-18324", "#redqueen")
    assert st == "empty" and job is None


def test_unrelated_repo_still_offers_while_sibling_ignored(_home):
    ignored = "SimonBarnett/agentic_fomprep"
    other = "SimonBarnett/bobiverse"
    _queue(
        _home,
        [
            _row(ignored, "MRB", 335, 1),
            _row(other, "FR", 6208, 2),
        ],
    )
    fi.handle_ignore_cmd(_home, ignored)
    # Late webhook re-adds ignored MRB alongside unrelated FR.
    _queue(
        _home,
        [
            _row(ignored, "MRB", 335, 1),
            _row(other, "FR", 6208, 2),
        ],
    )
    st, job = gitclaim.offer_focus_top(_home, "ionos-1", "#ionos")
    assert st == "ok" and job["repo"] == other and job["id"] == "#6208"


def test_apply_queue_event_skips_ignored_repo_synchronize(_home):
    repo = "SimonBarnett/agentic_fomprep"
    fi.handle_ignore_cmd(_home, repo)
    claim = gitclaim.GitClaim(
        repo=repo,
        task="MRB",
        id="#322",
        event="pull_request",
        action="synchronize",
        title="x",
        body="",
        labels=(),
        state="open",
        line=f"MRB {repo}#322",
        refs=(),
    )
    changed = gitclaim.apply_queue_event(_home, claim)
    assert changed in ("skipped", "noop")
    assert gitclaim.load_unaccepted(_home) == []


def test_repeated_ignore_repurges_leaked_rows(_home):
    repo = "o/z"
    fi.handle_ignore_cmd(_home, repo)
    _queue(_home, [_row(repo, "FR", 1, 1), _row("o/y", "FR", 2, 2)])
    msg = fi.handle_ignore_cmd(_home, repo)[0]
    assert "already ignoring" in msg
    assert "purged 1" in msg
    assert [r["repo"] for r in gitclaim.load_unaccepted(_home)] == ["o/y"]


def test_ack_after_ignore_refuses_and_frees_seat(_home):
    repo = "SimonBarnett/agentic_fomprep"
    row = _row(
        repo,
        "MRB",
        335,
        1,
        offered_to="redqueen-18324",
        offered_ts=gitclaim._utc_now(),
    )
    _queue(_home, [row])
    fi.handle_ignore_cmd(_home, repo)
    # Row purged; ACK must not create ack-missing hold for an ignored repo.
    out = shop_listen.handle_shop_worker_line(
        _home,
        nick="redqueen-18324",
        channel="#redqueen",
        body=f"ACK MRB {repo}#335",
        kind="agent",
        post_fn=lambda *a, **k: 204,
    )
    assert out.get("status") == "ignored"
    assert not gitclaim.seat_open_job(_home, "redqueen-18324")


def test_ack_refuses_when_ignored_row_still_in_queue(_home):
    repo = "o/ignored"
    other = "o/ok"
    _queue(_home, [_row(repo, "FR", 9, 1), _row(other, "FR", 10, 2)])
    fi.handle_ignore_cmd(_home, repo)
    # Force a leaked ignored row back into the queue (bypass apply_queue_event).
    _queue(_home, [_row(repo, "FR", 9, 1), _row(other, "FR", 10, 2)])
    st, job = shop_listen.accept_job_by_ref(
        _home,
        nick="ionos-1",
        channel="#ionos",
        repo=repo,
        task="FR",
        ident="#9",
    )
    assert st == "ignored" and job is None
    st2, job2 = shop_listen.accept_job_by_ref(
        _home,
        nick="ionos-2",
        channel="#ionos",
        repo=other,
        task="FR",
        ident="#10",
    )
    assert st2 == "ok" and job2["repo"] == other


def test_load_ignored_alias(_home):
    fi.handle_ignore_cmd(_home, "o/a")
    assert fi.load_ignored(_home) == fi.ignored_list(_home) == ["o/a"]


def test_requeue_reopened_skips_ignored(_home):
    """requeue_reopened_issue must pass home so ignored repos stay out of unaccepted."""
    repo = "SimonBarnett/agentic_fomprep"
    fi.handle_ignore_cmd(_home, repo)
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    claim = gitclaim.GitClaim(
        repo=repo,
        task="FR",
        id="#99",
        event="issues",
        action="reopened",
        title="x",
        body="",
        labels=(),
        state="open",
        line=f"FR {repo}#99",
        refs=(),
    )
    # Seed a done row that reopen would otherwise promote.
    doc["done"] = [_row(repo, "FR", 99, 1)]
    changed = gitclaim.requeue_reopened_issue(
        doc, claim, via="test", actor="simon", home=_home
    )
    assert changed == "skipped"
    assert doc.get("unaccepted") == []
    assert len(doc.get("done") or []) == 1


def test_ignored_ack_drops_accepted_row(_home):
    repo = "o/ignored"
    nick = "redqueen-1"
    accepted = _row(repo, "FR", 7, 1, nick=nick, accepted_ts=gitclaim._utc_now())
    _queue(_home, [], accepted=[accepted])
    fi.handle_ignore_cmd(_home, repo)
    # Force accepted row back (simulate purge lock timeout leaving accepted).
    _queue(_home, [], accepted=[accepted])
    st, job = shop_listen.accept_job_by_ref(
        _home,
        nick=nick,
        channel="#redqueen",
        repo=repo,
        task="FR",
        ident="#7",
    )
    assert st == "ignored" and job is None
    assert gitclaim.load_unaccepted(_home) == []
    assert not any(
        str(r.get("repo")) == repo and str(r.get("id")) == "#7" and str(r.get("nick")) == nick
        for r in gitclaim.load_accepted(_home)
        if isinstance(r, dict)
    )
