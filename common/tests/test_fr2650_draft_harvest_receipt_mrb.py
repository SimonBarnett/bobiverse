"""FR #2650: draft / harvest-receipt PRs must not become MRB via webhook;

PASS harvest-kind receipts record-only; closed-unmerged ACC purge is CLOSED not MERGED.
"""
from __future__ import annotations

from pathlib import Path

import gitclaim
import intake


REPO = "SimonBarnett/bobiverse"


def _pr_opened_payload(
    *,
    number: int,
    title: str,
    body: str,
    draft: bool = False,
    labels: list[str] | None = None,
) -> dict:
    labs = [{"name": n} for n in (labels or [])]
    return {
        "action": "opened",
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": number,
            "title": title,
            "body": body,
            "draft": draft,
            "html_url": f"https://github.com/{REPO}/pull/{number}",
            "labels": labs,
            "merged": False,
        },
    }


def test_fr2650_pass_harvest_is_worker_receipt():
    """499f0aa / ad4720a gap: PASS in harvest title was not a receipt marker."""
    title = "harvest: MRB #2642 PASS: merged PR #2642 (ProgressPreference EncodedCommand)"
    body = (
        "Session summary:\nMRB #2642 PASS: merged PR #2642\n"
        "_via-intake Invoke-BobiverseHarvest_"
    )
    assert intake.is_harvest_worker_receipt(kind="harvest", title=title, body=body)
    assert intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: MRB #2647 FAIL-superseded closed unmerged",
        body="Session summary:\nFAIL closed unmerged #2647",
    )


def test_fr2650_playbook_bare_merged_still_not_receipt():
    """MRB #2597: bare 'merged' / FR #N in a real playbook must still file."""
    assert not intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: tip utf8 write playbook",
        body="Session summary:\nAfter merged tip, restart only ircBob.",
    )


def test_fr2650_file_submission_pass_receipt_recorded(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: MRB #2642 PASS: merged PR #2642",
            "body": "Session summary:\nMRB #2642 PASS: merged\n_via-intake Invoke-BobiverseHarvest_",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_pass2650")
    assert rec["state"] == "receipt_recorded"
    assert filer.prs == []
    assert filer.issues == []


def test_fr2650_webhook_draft_harvest_receipt_produces_no_claim():
    """Live PR-opened webhook must match resync: draft harvest receipt → no MRB claim."""
    title = "harvest: MRB #2642 PASS: merged PR #2642"
    body = "Session summary:\nPASS\n_via-intake Invoke-BobiverseHarvest_"
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=2647,
            title=title,
            body=body,
            draft=True,
            labels=["via-intake", "skill"],
        ),
    )
    assert claim is None


def test_fr2650_webhook_draft_any_pr_produces_no_claim():
    """All draft open PRs skip MRB enqueue (resync already skips drafts)."""
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=99,
            title="fix(bob): WIP heal",
            body="Closes #98",
            draft=True,
        ),
    )
    assert claim is None


def test_fr2650_webhook_non_draft_harvest_receipt_produces_no_claim():
    """Intake harvest receipt cues (even if somehow non-draft) must not enqueue MRB."""
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=2648,
            title="harvest: twin of #2647",
            body=(
                "Session summary:\ntwin duplicate of #2647\n"
                "_via-intake Invoke-BobiverseHarvest_"
            ),
            draft=False,
            labels=["via-intake", "skill"],
        ),
    )
    assert claim is None


def test_fr2650_webhook_real_non_draft_pr_still_enqueues_mrb():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=2651,
            title="fix(jeeves): skip draft harvest receipts",
            body="Closes SimonBarnett/bobiverse#2650",
            draft=False,
        ),
    )
    assert claim is not None
    assert claim.task == "MRB"
    assert claim.id == "#2651"


def test_fr2650_apply_queue_draft_opened_adds_nothing(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=2647,
            title="harvest: MRB #2642 PASS: merged",
            body="Session summary:\nPASS\n_via-intake Invoke-BobiverseHarvest_",
            draft=True,
            labels=["via-intake", "skill"],
        ),
    )
    assert claim is None
    # Belt: even a forged non-None draft claim must not land if apply path guards.
    forged = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#2647",
        event="pull_request",
        action="opened",
        line="draft harvest",
    )
    # apply_queue_event with a normal non-draft claim still works:
    real = gitclaim.claim_from_payload(
        "pull_request",
        _pr_opened_payload(
            number=10,
            title="fix: real",
            body="Closes #9",
            draft=False,
        ),
    )
    assert real is not None
    st = gitclaim.apply_queue_event(home, real)
    assert st in ("added", "updated", "duplicate")
    rows = gitclaim.load_unaccepted(home)
    assert any(r.get("id") == "#10" for r in rows)
    assert not any(r.get("id") == "#2647" for r in rows)
    _ = forged  # unused; documents that claim_from_payload is the gate


def test_fr2650_purge_dead_mrb_accepted_closed_unmerged_is_closed_not_merged():
    """Closed-unmerged ACC MRB must not be stamped MERGED (queue lie after #2647)."""
    doc = {
        "accepted": [
            {
                "task": "MRB",
                "repo": REPO,
                "id": "#2647",
                "url": f"https://github.com/{REPO}/pull/2647",
                "nick": "marchhare-9524",
                "event": "pull_request",
            }
        ],
        "done": [],
        "unaccepted": [],
    }

    def pr_exists(repo: str, num: str) -> bool:
        return False  # closed or missing

    def pr_merged(repo: str, num: str) -> bool:
        return False  # closed unmerged

    n = gitclaim._purge_dead_mrb_accepted(
        doc, pr_exists=pr_exists, pr_merged=pr_merged, home=None
    )
    assert n == 1
    assert doc["accepted"] == []
    assert len(doc["done"]) == 1
    assert doc["done"][0]["result"] == "CLOSED"
    assert doc["done"][0].get("merged") is not True


def test_fr2650_purge_dead_mrb_accepted_merged_stays_merged():
    doc = {
        "accepted": [
            {
                "task": "MRB",
                "repo": REPO,
                "id": "#2642",
                "url": f"https://github.com/{REPO}/pull/2642",
                "nick": "marchhare-1",
            }
        ],
        "done": [],
        "unaccepted": [],
    }
    n = gitclaim._purge_dead_mrb_accepted(
        doc,
        pr_exists=lambda r, n: False,
        pr_merged=lambda r, n: True,
        home=None,
    )
    assert n == 1
    assert doc["done"][0]["result"] == "MERGED"


def test_fr2650_closed_unmerged_webhook_moves_acc_to_closed(tmp_path: Path):
    home = tmp_path / "chair"
    home.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "task": "MRB",
                    "repo": REPO,
                    "id": "#2647",
                    "url": f"https://github.com/{REPO}/pull/2647",
                    "nick": "marchhare-9524",
                    "event": "pull_request",
                    "action": "opened",
                }
            ],
            "done": [],
            "workers": {},
        },
    )
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 2647,
                "title": "harvest: MRB #2642 PASS",
                "body": "Session summary",
                "merged": False,
                "html_url": f"https://github.com/{REPO}/pull/2647",
            },
        },
    )
    assert claim is not None
    assert claim.merged is False
    st = gitclaim.apply_queue_event(home, claim)
    assert st in ("updated", "removed", "noop")
    q = gitclaim.load_queue(home) if hasattr(gitclaim, "load_queue") else None
    path = gitclaim.queue_path(home)
    import json

    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    assert not any(r.get("id") == "#2647" for r in (doc.get("accepted") or []))
    done = [r for r in (doc.get("done") or []) if r.get("id") == "#2647"]
    assert len(done) == 1
    assert done[0]["result"] == "CLOSED"
    _ = q
