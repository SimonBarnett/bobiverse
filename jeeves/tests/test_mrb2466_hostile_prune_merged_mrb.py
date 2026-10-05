"""MRB #2466 hostile gates for FR #2458 prune merged MRB from unaccepted."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim

REPO = "SimonBarnett/bobiverse"


def _queue(home: Path, *, unaccepted=None):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": [],
            "done": [],
        },
    )


def _mrb(num, **extra):
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": f"#{num}",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/{num}",
    }
    row.update(extra)
    return row


def test_mrb2466_norm_id_empty_and_non_digit():
    assert gitclaim._norm_row_id("") == ""
    assert gitclaim._norm_row_id(None) == ""
    assert gitclaim._norm_row_id("  ") == ""
    # non-digit tokens stay as-is (no false # prefix)
    assert gitclaim._norm_row_id("abc") == "abc"


def test_mrb2466_open_pulls_purge_skips_home_ledger_kill(tmp_path, monkeypatch):
    """Resync open_pulls pass must not pass home — stale mrb_done must not kill open PRs (#1585)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim.stamp_mrb_done(tmp_path, REPO, "#99")
    assert gitclaim.mrb_ledger_done_hold(tmp_path, REPO, "#99")
    doc = {"v": 1, "unaccepted": [_mrb(99), _mrb(2455)], "accepted": [], "done": []}
    # Same call shape as resync_from_github: open_pulls + fetched_repos, no home.
    n = gitclaim._purge_dead_mrb_unaccepted(
        doc,
        open_pulls={REPO: {"#99"}},
        fetched_repos={REPO},
    )
    assert n == 1
    ids = {gitclaim._norm_row_id(r.get("id")) for r in doc["unaccepted"]}
    assert ids == {"#99"}
    # Open #99 survived despite ledger stamp (no home on this purge path).
    assert gitclaim.mrb_ledger_done_hold(tmp_path, REPO, "#99")


def test_mrb2466_purge_dead_mrb_rows_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _queue(tmp_path, unaccepted=[_mrb(2455, merged=True), _mrb(99)])
    n = gitclaim.purge_dead_mrb_rows(tmp_path, pr_exists=lambda repo, num: str(num).lstrip("#") == "99")
    assert n >= 1
    doc = gitclaim._load_queue_unlocked(tmp_path)
    ids = {gitclaim._norm_row_id(r.get("id")) for r in (doc.get("unaccepted") or [])}
    assert "#2455" not in ids
    assert "#99" in ids


def test_mrb2466_public_queue_source_wires_purge():
    src = Path(bobreport.__file__).read_text(encoding="utf-8")
    assert "purge_dead_mrb_rows" in src
    assert "FR #2458" in src or "2458" in src
    assert "github_pr_exists_checker" in src


def test_mrb2466_remove_unaccepted_tasks_normalizes_task_case():
    doc = {
        "v": 1,
        "unaccepted": [
            _mrb(2455, id="2455", task="mrb"),
            _mrb(99, task="MRB"),
        ],
    }
    n = gitclaim._remove_unaccepted_tasks(doc, REPO, "#2455", {"MRB"})
    assert n == 1
    assert len(doc["unaccepted"]) == 1
    assert gitclaim._norm_row_id(doc["unaccepted"][0].get("id")) == "#99"
