"""FR #1682: skill-promote offerable path; bare skill stays SKIP_FR."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import gitclaim
import registered_machines

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import skill_promote_backlog  # noqa: E402


def _issue(num: int, title: str, labels: list[str], body: str = ""):
    return {
        "number": num,
        "title": title,
        "body": body,
        "state": "open",
        "labels": [{"name": x} for x in labels],
    }


def test_bare_skill_still_skip_fr():
    assert gitclaim.issue_skip_fr_reason(
        title="harvest: lesson", labels=["skill", "via-intake"]
    ) == "label:skill"
    assert gitclaim.issue_skip_fr_reason(title="harvest: only title") == "harvest_title"


def test_skill_promote_label_is_offerable():
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: promote open skill/harvest intake to skill-book PR",
            labels=["feature-request", "skill-promote", "via-intake"],
        )
        is None
    )
    # skill + skill-promote: promote wins (offerable).
    assert (
        gitclaim.issue_skip_fr_reason(
            title="FR: promote",
            labels=["skill", "skill-promote", "feature-request"],
        )
        is None
    )


def test_ensure_skill_promote_enqueues_existing_issue(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_SKILL_PROMOTE_THRESHOLD", "3")
    registered_machines.save_registered(tmp_path, {"marchhare"})
    receipts = [
        _issue(100 + i, f"harvest: lesson {i}", ["skill", "via-intake"]) for i in range(5)
    ]
    promote = _issue(
        200,
        "FR: promote open skill/harvest intake to skill-book PR",
        ["feature-request", "skill-promote"],
    )
    info = gitclaim.ensure_skill_promote_queue(
        tmp_path,
        open_issues=receipts + [promote],
        open_prs=[],
        create_issue=None,
        threshold=3,
    )
    assert info["action"] == "enqueued", info
    assert info["id"] == "#200"
    rows = gitclaim.load_unaccepted(tmp_path)
    assert any(gitclaim.row_is_skill_promote(r) for r in rows)
    # Second call is noop (already queued).
    info2 = gitclaim.ensure_skill_promote_queue(
        tmp_path,
        open_issues=receipts + [promote],
        open_prs=[],
        threshold=3,
    )
    assert info2["action"] == "noop" and info2["reason"] == "already_queued"


def test_ensure_skill_promote_noop_when_promote_pr_open(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    receipts = [_issue(10 + i, f"harvest: x{i}", ["skill"]) for i in range(20)]
    prs = [{"number": 9, "title": "harvest: batch promote skills", "labels": []}]
    info = gitclaim.ensure_skill_promote_queue(
        tmp_path, open_issues=receipts, open_prs=prs, threshold=5
    )
    assert info["action"] == "noop"
    assert info["reason"] == "promote_pr_open"


def test_ensure_creates_issue_when_callback_provided(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    receipts = [_issue(50 + i, f"harvest: y{i}", ["skill"]) for i in range(4)]
    created = {}

    def create_issue(title, body, labels):
        created["title"] = title
        created["labels"] = list(labels)
        return 777

    info = gitclaim.ensure_skill_promote_queue(
        tmp_path,
        open_issues=receipts,
        open_prs=[],
        create_issue=create_issue,
        threshold=3,
    )
    assert info["action"] == "enqueued"
    assert info["id"] == "#777"
    assert info.get("created_issue") == 777
    assert "skill-promote" in created["labels"]


def test_ensure_need_issue_without_create(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    receipts = [_issue(60 + i, f"harvest: z{i}", ["skill"]) for i in range(4)]
    info = gitclaim.ensure_skill_promote_queue(
        tmp_path, open_issues=receipts, open_prs=[], create_issue=None, threshold=3
    )
    assert info["action"] == "need_issue"


def test_monitor_queue_only_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = skill_promote_backlog.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert "no GITHUB_TOKEN" in " ".join(payload.get("notes") or "")


def test_monitor_dry_run_ok():
    # run_check dry-run path via script --help is covered by fr787; smoke import here.
    assert callable(skill_promote_backlog.check)
