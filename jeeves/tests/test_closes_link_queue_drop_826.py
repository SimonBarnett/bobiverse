"""t826u: Closes owner/repo#N links, and the queue row of a closed issue (FR #180 point 4)."""
from __future__ import annotations

import gitclaim
from gitclaim import GitClaim, apply_queue_event, claim_from_payload, extract_closes_issue_ids, load_unaccepted

REPO = "SimonBarnett/bobiverse"


def _rows(home):
    return [(r["task"], r["id"]) for r in load_unaccepted(home)]


def _pr_payload(action="opened", body="", merged=False, number=9):
    return {"action": action, "repository": {"full_name": REPO},
            "pull_request": {"number": number, "title": "FR #5 thing", "body": body, "merged": merged, "html_url": "u"}}


def test_closes_regex_forms():
    assert extract_closes_issue_ids("Closes #5") == ("#5",)
    assert extract_closes_issue_ids("closes SimonBarnett/bobiverse#5") == ("#5",)
    assert extract_closes_issue_ids("Fixes a/b#7 and Resolves #8") == ("#7", "#8")
    assert extract_closes_issue_ids("Closes #5", "Refs #5") == ("#5",)


def test_closes_link_to_another_repo_is_ignored_when_repo_given():
    assert extract_closes_issue_ids("Closes other/repo#5", repo=REPO) == ()
    assert extract_closes_issue_ids("Closes simonbarnett/BOBIVERSE#5", repo=REPO) == ("#5",)
    assert extract_closes_issue_ids("Closes other/repo#5") == ("#5",)  # no repo filter: unchanged behaviour


def test_pr_payload_with_full_closes_form_carries_the_ref():
    c = claim_from_payload("pull_request", _pr_payload(body=f"Closes {REPO}#5\n\nevidence"))
    assert c.refs == ("#5",)
    c = claim_from_payload("pull_request", _pr_payload(body="Closes other/repo#5"))
    assert c.refs == ()


def test_pr_open_supersedes_fr_then_merge_queues_per_issue_uat(tmp_path):
    # mrb-664-fix / FR #628: merge queues UAT #<issue>; MRB row is removed.
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="FR", id="#5", event="issues", action="opened", line="l"))
    assert ("FR", "#5") in _rows(tmp_path)
    apply_queue_event(tmp_path, claim_from_payload("pull_request", _pr_payload(body=f"Closes {REPO}#5")))
    rows = _rows(tmp_path)
    assert ("FR", "#5") not in rows and ("MRB", "#9") in rows
    apply_queue_event(tmp_path, claim_from_payload("pull_request", _pr_payload("closed", f"Closes {REPO}#5", merged=True)))
    rows = _rows(tmp_path)
    assert ("UAT", "#5") in rows and ("MRB", "#9") not in rows
    # Issue-closed still drops a manually opened UAT that was not merge-sourced (t826u).
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="UAT", id="#6", event="issues", action="opened", line="l"))
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="FR", id="#6", event="issues", action="closed", line="l"))
    assert ("UAT", "#6") not in _rows(tmp_path)


def test_issue_closed_drops_fr_and_pr_rows_and_manual_uat_rows(tmp_path):
    for task in ("FR", "PR", "UAT"):
        apply_queue_event(tmp_path, GitClaim(repo=REPO, task=task, id="#6", event="issues", action="opened", line="l"))
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="FR", id="#6", event="issues", action="closed", line="l"))
    assert [r for r in _rows(tmp_path) if r[1] == "#6"] == []


def test_other_issues_rows_survive_a_close(tmp_path):
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="FR", id="#7", event="issues", action="opened", line="l"))
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="FR", id="#8", event="issues", action="opened", line="l"))
    apply_queue_event(tmp_path, GitClaim(repo=REPO, task="FR", id="#7", event="issues", action="closed", line="l"))
    assert _rows(tmp_path) == [("FR", "#8")]