"""FR #1729: monitor open_skill_without_promote_pr after #1682 offer-all skill path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import skill_promote_backlog as spb  # noqa: E402


def _issue(num: int, title: str, labels: list[str], body: str = ""):
    return {
        "number": num,
        "title": title,
        "body": body,
        "state": "open",
        "labels": [{"name": x} for x in labels],
    }


def _pr(num: int, title: str, head_ref: str):
    return {
        "number": num,
        "title": title,
        "head": {"ref": head_ref},
        "labels": [],
    }


def test_is_skill_receipt_label_and_harvest_title():
    assert spb.is_skill_receipt(title="harvest: lesson", labels=["via-intake"])
    assert spb.is_skill_receipt(title="FR: something", labels=["skill", "via-intake"])
    assert not spb.is_skill_receipt(title="FR: product", labels=["feature-request"])


def test_is_promote_pr_harvest_branch_or_title():
    assert spb.is_promote_pr(_pr(1, "harvest: bob job book", "harvest/bob-job"))
    assert spb.is_promote_pr(_pr(2, "fix(mrb-1): nits", "harvest/mrb-nits"))
    assert spb.is_promote_pr(_pr(3, "harvest(jeeves): skill-offer idle", "fr-1705"))
    assert not spb.is_promote_pr(_pr(4, "FR #99: product", "fr-99-product"))


def test_finding_when_many_skills_and_no_promote_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_SKILL_PROMOTE_THRESHOLD", "3")
    monkeypatch.setenv("GH_TOKEN", "fake")
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    receipts = [_issue(100 + i, f"harvest: lesson {i}", ["skill", "via-intake"]) for i in range(5)]
    monkeypatch.setattr(spb, "_fetch_open_lists", lambda repo, token: (receipts, []))
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = spb.check(args)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["open_skill_without_promote_pr"] == 1
    assert payload["skill_count"] == 5
    assert any("open_skill_without_promote_pr" in f for f in payload["findings"])


def test_ok_when_harvest_pr_open(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_SKILL_PROMOTE_THRESHOLD", "3")
    monkeypatch.setenv("GH_TOKEN", "fake")
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    receipts = [_issue(100 + i, f"harvest: lesson {i}", ["skill"]) for i in range(5)]
    prs = [_pr(9, "harvest: consolidate jeeves monitor", "harvest/jeeves-monitor")]
    monkeypatch.setattr(spb, "_fetch_open_lists", lambda repo, token: (receipts, prs))
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = spb.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["promote_pr_open"] is True
    assert payload["open_skill_without_promote_pr"] == 0


def test_ok_when_skill_fr_queued(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_SKILL_PROMOTE_THRESHOLD", "3")
    monkeypatch.setenv("GH_TOKEN", "fake")
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "task": "FR",
                        "id": "#200",
                        "title": "harvest: lesson queued",
                        "labels": ["skill", "via-intake"],
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    receipts = [_issue(100 + i, f"harvest: lesson {i}", ["skill"]) for i in range(5)]
    monkeypatch.setattr(spb, "_fetch_open_lists", lambda repo, token: (receipts, []))
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = spb.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["queued_skill_fr_count"] >= 1
    assert payload["open_skill_without_promote_pr"] == 0


def test_no_token_queue_only_ok(tmp_path, monkeypatch):
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
    payload, code = spb.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert "no GITHUB_TOKEN" in " ".join(payload.get("notes") or "")


def test_dry_run_via_main():
    assert spb.main(["--dry-run"]) == 0
