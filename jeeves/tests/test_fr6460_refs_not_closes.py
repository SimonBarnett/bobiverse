"""FR #6460: Refs must not dequeue or supersede an open FR (class of #6451 / docs/mrb #6452)."""
from __future__ import annotations

from gitclaim import (
    GitClaim,
    apply_queue_event,
    claim_from_payload,
    extract_closes_issue_ids,
    fr_is_superseded,
    load_unaccepted,
    _load_queue_unlocked,
    _write_queue,
    queue_path,
)

REPO = "SimonBarnett/bobiverse"


def _rows(home):
    return [(r["task"], r["id"]) for r in load_unaccepted(home)]


def _pr_payload(*, action="opened", body="", merged=False, number=6452, title="docs/mrb-6450: pins"):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": number,
            "title": title,
            "body": body,
            "merged": merged,
            "html_url": f"https://github.com/{REPO}/pull/{number}",
            "draft": False,
            "user": {"login": "bobiverse"},
        },
    }


def test_fr6460_extract_refs_alone_empty():
    assert extract_closes_issue_ids("Refs SimonBarnett/bobiverse#6451") == ()
    assert extract_closes_issue_ids("Ref #6451") == ()
    assert extract_closes_issue_ids("refs owner/repo#9") == ()
    assert extract_closes_issue_ids("Closes #6451") == ("#6451",)
    assert extract_closes_issue_ids("Fixes #1\nRefs #2") == ("#1",)


def test_fr6460_docs_mrb_pin_claim_has_no_refs():
    body = (
        "Refs SimonBarnett/bobiverse#6450\n"
        "Refs SimonBarnett/bobiverse#6441\n"
        "Refs SimonBarnett/bobiverse#6451\n"
    )
    c = claim_from_payload("pull_request", _pr_payload(body=body))
    # docs/mrb pins often skip MRB enqueue; either way refs must be empty.
    assert c is None or c.refs == ()


def test_fr6460_merged_refs_only_keeps_unaccepted_fr(tmp_path):
    apply_queue_event(
        tmp_path,
        GitClaim(repo=REPO, task="FR", id="#6451", event="issues", action="opened", line="l"),
    )
    assert ("FR", "#6451") in _rows(tmp_path)
    body = "Refs SimonBarnett/bobiverse#6451\n\nAdditive hostile tests."
    apply_queue_event(
        tmp_path,
        claim_from_payload(
            "pull_request",
            _pr_payload(action="closed", body=body, merged=True, number=6452),
        )
        or GitClaim(
            repo=REPO,
            task="MRB",
            id="#6452",
            event="pull_request",
            action="closed",
            line="l",
            title="docs/mrb-6450",
            body=body,
            refs=extract_closes_issue_ids(body, repo=REPO),
            merged=True,
        ),
    )
    assert ("FR", "#6451") in _rows(tmp_path)


def test_fr6460_merged_closes_still_dequeues(tmp_path):
    apply_queue_event(
        tmp_path,
        GitClaim(repo=REPO, task="FR", id="#6451", event="issues", action="opened", line="l"),
    )
    apply_queue_event(
        tmp_path,
        GitClaim(
            repo=REPO,
            task="MRB",
            id="#6459",
            event="pull_request",
            action="closed",
            line="l",
            title="FR #6451 wire",
            body="Closes SimonBarnett/bobiverse#6451",
            refs=("#6451",),
            merged=True,
        ),
    )
    assert ("FR", "#6451") not in _rows(tmp_path)


def test_fr6460_open_refs_pr_does_not_supersede(tmp_path):
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    open_closes = {REPO: set(extract_closes_issue_ids("Refs #6451", repo=REPO))}
    assert open_closes[REPO] == set()
    assert fr_is_superseded(doc, REPO, "#6451", open_closes=open_closes) is False


def test_fr6460_open_closes_pr_still_supersedes(tmp_path):
    doc = {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    open_closes = {REPO: set(extract_closes_issue_ids("Closes #6451", repo=REPO))}
    assert open_closes[REPO] == {"#6451"}
    assert fr_is_superseded(doc, REPO, "#6451", open_closes=open_closes) is True


def test_fr6460_product_fr_body_with_parent_refs_still_enqueues(tmp_path):
    """Issue body ## Parent / Refs lines must not block FR enqueue (class of #6451)."""
    body = (
        "## Parent\n"
        "Refs SimonBarnett/bobiverse#6441\n"
        "Refs SimonBarnett/bobiverse#6440\n\n"
        "## Goal\nWire HTTP auth.\n"
    )
    payload = {
        "action": "opened",
        "repository": {"full_name": REPO},
        "issue": {
            "number": 6451,
            "title": "Wire jeeves_settings_http to FR #6441",
            "body": body,
            "html_url": f"https://github.com/{REPO}/issues/6451",
            "state": "open",
            "labels": [{"name": "feature-request"}, {"name": "via-intake"}],
            "user": {"login": "bobiverse"},
        },
    }
    c = claim_from_payload("issues", payload)
    assert c is not None
    assert c.task == "FR"
    assert c.id == "#6451"
    apply_queue_event(tmp_path, c)
    assert ("FR", "#6451") in _rows(tmp_path)
