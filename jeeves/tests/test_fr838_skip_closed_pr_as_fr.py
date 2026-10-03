"""FR #838: never offer a GitHub pull request (open or closed) as an FR job."""
from __future__ import annotations

import gitclaim


REPO = "SimonBarnett/bobiverse"


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )


def _fr_row(*, num: int, title: str, body: str = "", url: str = "", event: str = "issues", **extra):
    row = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": 1,
        "ts": "2026-10-03T12:00:00Z",
        "title": title,
        "body": body,
        "event": event,
        "action": "opened",
        "line": title,
    }
    if url:
        row["url"] = url
    row.update(extra)
    return row


def test_fr_row_is_pull_request_structural():
    # Closed Fixes PR #808 re-offered as FR (incident shape).
    pr_shaped = _fr_row(
        num=808,
        title="fix(bobiverse#795): retire archived repos from intake allow-list",
        body="Closes SimonBarnett/bobiverse#795\n",
    )
    assert gitclaim.fr_row_is_pull_request(pr_shaped) is True

    pull_url = _fr_row(
        num=808,
        title="anything",
        url="https://github.com/SimonBarnett/bobiverse/pull/808",
    )
    assert gitclaim.fr_row_is_pull_request(pull_url) is True

    event_pr = _fr_row(num=808, title="real looking FR title", event="pull_request")
    assert gitclaim.fr_row_is_pull_request(event_pr) is True

    real_fr = _fr_row(
        num=838,
        title="Chair offered closed PR #808 as FR after MRB supersede-close",
        body="Skip CLOSED pull requests when building FR offer queue.",
    )
    assert gitclaim.fr_row_is_pull_request(real_fr) is False


def test_fr_row_is_pull_request_via_pr_exists():
    row = _fr_row(num=808, title="Chair gap follow-up without conventional title")

    def pr_exists(repo, num):
        return repo == REPO and str(num) == "808"

    assert gitclaim.fr_row_is_pull_request(row, pr_exists=pr_exists) is True
    assert gitclaim.fr_row_is_pull_request(row, pr_exists=lambda r, n: False) is False


def test_offer_focus_top_skips_closed_pr_as_fr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda home: {"marchhare-41928"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda home: {})
    _queue(
        tmp_path,
        [
            _fr_row(
                num=808,
                title="fix(bobiverse#795): retire archived repos from intake allow-list",
                body="Closes SimonBarnett/bobiverse#795",
            ),
            _fr_row(
                num=900,
                title="FR: real implementable work",
                body="Do the thing.",
                **{"seq": 2},
            ),
        ],
    )
    # Patch ordered_unaccepted to preserve seq order without focus file.
    monkeypatch.setattr(
        gitclaim,
        "ordered_unaccepted",
        lambda home, rows: sorted(rows, key=gitclaim._sort_key),
    )
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-41928", "#marchhare")
    assert st == "ok"
    assert job is not None
    assert job["id"] == "#900"
    assert "808" not in str(job.get("id"))


def test_offer_focus_top_skips_when_pr_exists_says_pull(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda home: {"marchhare-41928"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda home: {})
    monkeypatch.setattr(
        gitclaim,
        "ordered_unaccepted",
        lambda home, rows: sorted(rows, key=gitclaim._sort_key),
    )
    _queue(
        tmp_path,
        [
            _fr_row(num=808, title="Ambiguous title that is actually a pull"),
            _fr_row(num=901, title="FR: next real job", **{"seq": 2}),
        ],
    )

    def pr_exists(repo, num):
        return str(num) == "808"

    st, job = gitclaim.offer_focus_top(
        tmp_path, "marchhare-41928", "#marchhare", pr_exists=pr_exists
    )
    assert st == "ok"
    assert job["id"] == "#901"


def test_prune_drops_pr_shaped_fr_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(
        tmp_path,
        [
            _fr_row(
                num=808,
                title="fix(bobiverse#795): retire archived allow-list",
                body="Closes SimonBarnett/bobiverse#795",
            ),
            _fr_row(num=902, title="FR: keep me", **{"seq": 2}),
        ],
    )
    out = gitclaim.prune_unassignable_queue(tmp_path)
    assert out.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    assert [r["id"] for r in rows] == ["#902"]


def test_closed_unmerged_pr_restores_linked_issue_not_pr_id(tmp_path, monkeypatch):
    """pull_request closed (merged=false) must restore Closes refs as FR, never the PR number."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # Seed an MRB for the open PR.
    _queue(
        tmp_path,
        [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#808",
                "seq": 1,
                "ts": "2026-10-03T12:00:00Z",
                "url": f"https://github.com/{REPO}/pull/808",
                "refs": ["#795"],
            }
        ],
    )
    payload = {
        "action": "closed",
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": 808,
            "title": "fix(bobiverse#795): retire archived repos from intake allow-list",
            "body": "Closes SimonBarnett/bobiverse#795\n",
            "merged": False,
            "html_url": f"https://github.com/{REPO}/pull/808",
        },
    }
    claim = gitclaim.claim_from_payload("pull_request", payload)
    assert claim is not None and claim.task == "MRB" and claim.id == "#808"
    assert gitclaim.apply_queue_event(tmp_path, claim) == "updated"
    rows = gitclaim.load_unaccepted(tmp_path)
    ids = {(r["task"], r["id"]) for r in rows}
    assert ("MRB", "#808") not in ids
    assert ("FR", "#808") not in ids
    assert ("FR", "#795") in ids


def test_issues_claim_skips_pull_request_blob():
    """issues webhook payloads that are actually PRs (pull_request key) must not become FR."""
    payload = {
        "action": "opened",
        "repository": {"full_name": REPO},
        "issue": {
            "number": 808,
            "title": "fix(bobiverse#795): retire archived repos",
            "body": "Closes #795",
            "state": "open",
            "labels": [],
            "pull_request": {"url": f"https://api.github.com/repos/{REPO}/pulls/808"},
        },
    }
    assert gitclaim.claim_from_payload("issues", payload) is None

def test_assign_row_refuses_pr_shaped_fr(tmp_path, monkeypatch):
    """MRB #850 fix: assign_row keeps FR #838 refuse after rebase onto t853u main."""
    import registered_machines

    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos"})
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda home: {"marchhare-35600"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda home: {})
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    _queue(
        tmp_path,
        [
            _fr_row(
                num=808,
                title="fix(bobiverse#795): retire archived repos from intake allow-list",
            )
        ],
    )
    st, why = gitclaim.assign_row(tmp_path, "marchhare-35600", REPO, "FR", "#808")
    assert st == "refused"
    assert "pull request" in str(why).lower() or "838" in str(why)


def test_offer_top_skips_pr_shaped_and_keeps_real_fr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda home: {"marchhare-35600"})
    monkeypatch.setattr(gitclaim, "ledger_load", lambda home: {})
    _queue(
        tmp_path,
        [
            _fr_row(
                num=808,
                title="fix(bobiverse#795): retire archived repos from intake allow-list",
            ),
            _fr_row(num=902, title="FR: real implementable work", body="Do it.", **{"seq": 2}),
        ],
    )
    st, job = gitclaim.offer_top(tmp_path, "marchhare-35600", "#marchhare")
    assert st == "ok" and job is not None and job["id"] == "#902"
