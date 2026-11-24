"""FR #9552: auto-close fr-digest when last open Depends-on child closes."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fr_digest_auto_close as fac  # noqa: E402

REPO = "SimonBarnett/bobiverse"


def _issue(num: int, *, labels=(), state="open", body="", repo=REPO, **kw):
    row = {
        "number": num,
        "repo": repo,
        "state": state,
        "labels": [{"name": x} for x in labels],
        "body": body,
        "title": f"Issue {num}",
    }
    row.update(kw)
    return row


def test_marker_on_tip():
    assert fac.bob_fr9552_auto_close_digest is True


def test_last_child_close_closes_digest():
    digest = _issue(9259, labels=("fr-digest", "feature-request"))
    child = _issue(9403, body="Depends-on: #9259\n\nwork")
    closed: list[tuple] = []

    def fetch(repo, num):
        assert repo == REPO
        return {9259: digest, 9403: child}.get(int(num))

    def list_open(repo):
        # Only digest still open; child already closed (not in list).
        return [digest]

    def close(repo, num, comment):
        closed.append((repo, num, comment))

    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=9403,
        child_body=child["body"],
        fetch_issue=fetch,
        list_open_issues=list_open,
        close_issue=close,
    )
    assert len(results) == 1
    assert results[0]["action"] == "closed"
    assert results[0]["number"] == 9259
    assert closed == [
        (
            REPO,
            9259,
            fac.close_comment(REPO, 9403),
        )
    ]
    assert "FR #9552" in closed[0][2]
    assert "#9403" in closed[0][2]


def test_sibling_still_open_keeps_digest_open():
    digest = _issue(9259, labels=("fr-digest",))
    sibling = _issue(9261, body="Depends-on: #9259\n")
    closed: list = []

    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=9403,
        child_body="Depends-on: #9259",
        fetch_issue=lambda r, n: digest if int(n) == 9259 else None,
        list_open_issues=lambda r: [digest, sibling],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "skipped_open_children"
    assert closed == []
    assert any("9261" in c for c in results[0].get("children") or [])


def test_held_digest_not_closed():
    digest = _issue(9259, labels=("fr-digest", "hold"))
    closed: list = []
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=9403,
        child_body="Depends-on: #9259",
        fetch_issue=lambda r, n: digest,
        list_open_issues=lambda r: [digest],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "skipped_held"
    assert closed == []


def test_already_closed_digest_idempotent():
    digest = _issue(9259, labels=("fr-digest",), state="closed")
    closed: list = []
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=9403,
        child_body="Depends-on: #9259",
        fetch_issue=lambda r, n: digest,
        list_open_issues=lambda r: [],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "skipped_already_closed"
    assert closed == []


def test_non_digest_parent_not_closed():
    parent = _issue(8807, labels=("feature-request",))
    closed: list = []
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=9403,
        child_body="Depends-on: #8807",
        fetch_issue=lambda r, n: parent,
        list_open_issues=lambda r: [parent],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "skipped_not_digest"
    assert closed == []


def test_exclude_just_closed_child_from_open_list():
    """Stale open list may still show the just-closed child; exclude it."""
    digest = _issue(9259, labels=("fr-digest",))
    stale_child = _issue(9403, body="Depends-on: #9259", state="open")
    closed: list = []
    results = fac.maybe_close_fr_digest_parents(
        child_repo=REPO,
        child_number=9403,
        child_body="Depends-on: #9259",
        fetch_issue=lambda r, n: digest if int(n) == 9259 else stale_child,
        list_open_issues=lambda r: [digest, stale_child],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "closed"
    assert closed and closed[0][1] == 9259


def test_reconcile_closes_orphan_digest_with_no_children():
    digest = _issue(9259, labels=("fr-digest",))
    closed: list = []
    results = fac.reconcile_open_fr_digests(
        REPO,
        list_open_digest_issues=lambda r: [digest],
        list_open_issues=lambda r: [digest],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "closed"
    assert closed and closed[0][1] == 9259


def test_reconcile_keeps_digest_with_open_child():
    digest = _issue(9259, labels=("fr-digest",))
    child = _issue(9261, body="Depends-on: #9259")
    closed: list = []
    results = fac.reconcile_open_fr_digests(
        REPO,
        list_open_digest_issues=lambda r: [digest],
        list_open_issues=lambda r: [digest, child],
        close_issue=lambda *a: closed.append(a),
    )
    assert results[0]["action"] == "skipped_open_children"
    assert closed == []


def test_on_issue_closed_entry_no_depends_returns_empty():
    assert (
        fac.on_issue_closed(
            REPO,
            9403,
            body="no depends here",
            fetch_issue=lambda *a: None,
            list_open_issues=lambda r: [],
            close_issue=lambda *a: None,
        )
        == []
    )


def test_fake_filer_close_issue():
    from intake import FakeGitHubFiler

    fake = FakeGitHubFiler()
    created = fake.create_issue(REPO, "digest", "body", ["fr-digest"])
    n = int(created["number"])
    fake.close_issue(REPO, n, comment="done")
    assert fake.get_issue_state(REPO, n) == "closed"
    assert any("done" in str(c.get("body")) for c in fake.comments)
