"""FR #9635: resync + monitor heal enqueue missing MRB (incl. lesson tips).

Live pain: MERGEABLE harvest tip #9631 had no MRB queue row until monitor
``!assign``. Resync already enqueues; monitor now heals (default ON) so EXIT 1
correlates with enqueue in the same check cycle.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import gitclaim
from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import open_pr_mrb_missing as opmm  # noqa: E402

REPO_NAME = "SimonBarnett/bobiverse"


def _lesson_pr(n: int = 9631):
    return {
        "number": n,
        "title": "lesson(bobiverse-jeeves-monitor): CAST IRON interventions",
        "body": "## Summary\nHarvest CAST IRON\n\n## Lesson\n- every MONITORING intervention FR\n",
        "html_url": f"https://github.com/{REPO_NAME}/pull/{n}",
        "state": "open",
        "draft": False,
        "user": {"login": "u"},
        "head": {"ref": "harvest/cast-iron-intervene", "sha": "abc"},
        "labels": [],
        "base": {"ref": "main", "repo": {"full_name": REPO_NAME}},
    }


def _product_pr(n: int = 8353):
    return {
        "number": n,
        "title": "FR #8348: enable Priority",
        "body": f"Closes {REPO_NAME}#8348",
        "html_url": f"https://github.com/{REPO_NAME}/pull/{n}",
        "state": "open",
        "draft": False,
        "user": {"login": "u"},
        "base": {"ref": "main", "repo": {"full_name": REPO_NAME}},
    }


def test_fr9635_resync_enqueues_lesson_tip(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )

    def _fetch(url: str):
        if "/pulls" in url and "state=closed" not in url:
            return [_lesson_pr(9631)]
        if "/issues" in url:
            return []
        return []

    res = gitclaim.resync_from_github(
        tmp_path, [REPO_NAME], fetch_json=_fetch
    )
    assert res.get("ok") is True
    rows = gitclaim.load_unaccepted(tmp_path)
    mrb = [r for r in rows if r.get("task") == "MRB" and r.get("id") == "#9631"]
    assert len(mrb) == 1
    assert "pull/9631" in str(mrb[0].get("url") or "")
    assert gitclaim.open_pr_expects_mrb_or_fix_row(_lesson_pr(9631)) is True


def test_fr9635_heal_enqueues_lesson_and_product(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    pulls = [_lesson_pr(9631), _product_pr(8353)]
    before = gitclaim.list_open_prs_missing_mrb(pulls, {"unaccepted": []}, repo=REPO_NAME)
    assert {m["number"] for m in before} == {9631, 8353}

    out = gitclaim.heal_open_prs_missing_mrb(tmp_path, pulls, repo=REPO_NAME)
    assert out["ok"] is True
    assert out["added"] == 2
    assert out["missing_after"] == 0
    rows = gitclaim.load_unaccepted(tmp_path)
    ids = {(r.get("task"), r.get("id")) for r in rows}
    assert ("MRB", "#9631") in ids
    assert ("MRB", "#8353") in ids


def test_fr9635_monitor_heal_clears_finding(monkeypatch, tmp_path):
    (tmp_path / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    fixture = tmp_path / "pulls.json"
    fixture.write_text(
        json.dumps({"repo": REPO_NAME, "pulls": [_lesson_pr(9631)]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE", str(fixture))
    args = SimpleNamespace(
        chair_home=str(tmp_path),
        digest_home="",
        dry_run=False,
        heal=True,
        heal_dry_run=False,
    )
    payload, code = opmm.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["missing_count"] == 0
    assert payload.get("heal", {}).get("added") == 1
    q = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert any(
        r.get("task") == "MRB" and r.get("id") == "#9631"
        for r in (q.get("unaccepted") or [])
    )


def test_fr9635_monitor_no_heal_still_finds(monkeypatch, tmp_path):
    (tmp_path / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": [], "accepted": [], "done": []}),
        encoding="utf-8",
    )
    fixture = tmp_path / "pulls.json"
    fixture.write_text(
        json.dumps({"repo": REPO_NAME, "pulls": [_lesson_pr(9631)]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE", str(fixture))
    args = SimpleNamespace(
        chair_home=str(tmp_path), digest_home="", dry_run=False, heal=False
    )
    payload, code = opmm.check(args)
    assert code == 1
    assert payload["missing_count"] == 1
    q = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))
    assert not (q.get("unaccepted") or [])
