"""FR #3275: issues/PR labeled|unlabeled update queue labels with zero REST."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/bobiverse"


def _issue_payload(action: str, num: int, *, labels=None, title: str | None = None, state: str = "open"):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "label": {"name": (labels or ["x"])[-1] if action in ("labeled", "unlabeled") else "x"},
        "issue": {
            "number": num,
            "title": title or f"issue {num}",
            "body": "body",
            "state": state,
            "labels": [{"name": n} for n in (labels or [])],
        },
    }


def _pr_payload(action: str, num: int, *, labels=None, title: str | None = None):
    return {
        "action": action,
        "repository": {"full_name": REPO},
        "label": {"name": (labels or ["x"])[-1] if action in ("labeled", "unlabeled") else "x"},
        "pull_request": {
            "number": num,
            "title": title or f"pr {num}",
            "body": f"Closes {REPO}#1",
            "merged": False,
            "draft": False,
            "state": "open",
            "html_url": f"https://github.com/{REPO}/pull/{num}",
            "labels": [{"name": n} for n in (labels or [])],
        },
    }


def _seed_fr(home: Path, num: int, *, labels=None, title: str = "seed fr"):
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id=f"#{num}",
        event="issues",
        action="opened",
        line=title,
        title=title,
        body="body",
        labels=tuple(labels or ()),
        state="open",
    )
    assert gitclaim.apply_queue_event(home, claim) in ("added", "duplicate")


def _seed_mrb(home: Path, num: int, *, labels=None):
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id=f"#{num}",
        event="pull_request",
        action="opened",
        line=f"pr {num}",
        title=f"pr {num}",
        body="",
        labels=tuple(labels or ()),
        state="open",
    )
    assert gitclaim.apply_queue_event(home, claim) in ("added", "duplicate", "updated")


def test_claim_from_payload_labeled_unlabeled_returns_claim():
    fr = gitclaim.claim_from_payload(
        "issues", _issue_payload("labeled", 9, labels=["feature-request", "via-intake"])
    )
    assert fr is not None
    assert fr.task == "FR" and fr.id == "#9"
    assert fr.action == "labeled"
    assert set(fr.labels) == {"feature-request", "via-intake"}

    pr = gitclaim.claim_from_payload(
        "pull_request", _pr_payload("unlabeled", 12, labels=["via-intake"])
    )
    assert pr is not None
    assert pr.task == "MRB" and pr.id == "#12"
    assert pr.action == "unlabeled"
    assert list(pr.labels) == ["via-intake"]


def test_labeled_unlabeled_burst_zero_rest_updates_queue_labels(tmp_path: Path):
    calls: list[str] = []

    def spy_fetch(url: str):
        calls.append(url)
        raise AssertionError(f"REST must not run on webhook path: {url}")

    _seed_fr(tmp_path, 20, labels=["feature-request"], title="live FR")
    _seed_mrb(tmp_path, 30, labels=[])

    events = [
        ("issues", _issue_payload("labeled", 20, labels=["feature-request", "skill"], title="live FR")),
        ("issues", _issue_payload("unlabeled", 20, labels=["feature-request"], title="live FR")),
        ("pull_request", _pr_payload("labeled", 30, labels=["harvest-lesson"])),
        ("pull_request", _pr_payload("unlabeled", 30, labels=[])),
    ]
    for ev, payload in events:
        out = bobreport.apply_git_webhook(tmp_path, ev, payload)
        assert out.ok, out.err

    rows = { (r["task"], r["id"]): r for r in gitclaim.load_unaccepted(tmp_path) }
    assert ("FR", "#20") in rows
    assert set(rows[("FR", "#20")].get("labels") or []) == {"feature-request"}
    assert ("MRB", "#30") in rows
    assert list(rows[("MRB", "#30")].get("labels") or []) == []
    assert calls == []


def test_labeled_needs_human_removes_fr_unlabeled_requeues(tmp_path: Path):
    _seed_fr(tmp_path, 40, labels=["feature-request"], title="gate me")

    out = bobreport.apply_git_webhook(
        tmp_path,
        "issues",
        _issue_payload("labeled", 40, labels=["feature-request", "needs-human"], title="gate me"),
    )
    assert out.ok, out.err
    ids = {(r["task"], r["id"]) for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("FR", "#40") not in ids

    out2 = bobreport.apply_git_webhook(
        tmp_path,
        "issues",
        _issue_payload("unlabeled", 40, labels=["feature-request"], title="gate me"),
    )
    assert out2.ok, out2.err
    rows = [r for r in gitclaim.load_unaccepted(tmp_path) if r["id"] == "#40" and r["task"] == "FR"]
    assert len(rows) == 1
    assert set(rows[0].get("labels") or []) == {"feature-request"}


def test_labeled_updates_accepted_row_labels(tmp_path: Path):
    _seed_fr(tmp_path, 50, labels=["feature-request"], title="accepted fr")
    doc = gitclaim.load_queue(tmp_path)
    row = doc["unaccepted"].pop(0)
    doc["accepted"].append(row)
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)

    out = bobreport.apply_git_webhook(
        tmp_path,
        "issues",
        _issue_payload("labeled", 50, labels=["feature-request", "skill"], title="accepted fr"),
    )
    assert out.ok, out.err
    acc = gitclaim.load_accepted(tmp_path)
    assert len(acc) == 1
    assert set(acc[0].get("labels") or []) == {"feature-request", "skill"}
