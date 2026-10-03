"""FR #818: refuse / purge per-PR UAT; only UAT owner/repo#0 with repo_uat is real work.

Closes the gap class also seen on #821 (UAT #813 mrb-fix) and #823 (self-UAT #815).
"""
from __future__ import annotations

from pathlib import Path

import gitclaim

REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _uat(ident: str, *, repo_uat: bool = False, seq: int = 1, **extra) -> dict:
    row = {
        "repo": REPO,
        "task": "UAT",
        "id": ident,
        "line": f"UAT {REPO}{ident}",
        "url": f"https://github.com/{REPO}/pull/{ident.lstrip('#')}" if ident not in ("#0", "0") else f"https://github.com/{REPO}",
        "seq": seq,
    }
    if repo_uat:
        row["repo_uat"] = True
    row.update(extra)
    return row


def test_is_repo_uat_requires_repo_uat_and_id_zero():
    assert gitclaim.is_repo_uat(_uat("#0", repo_uat=True)) is True
    assert gitclaim.is_repo_uat(_uat("0", repo_uat=True)) is True
    assert gitclaim.is_repo_uat(_uat("#802")) is False
    assert gitclaim.is_repo_uat(_uat("#802", repo_uat=True)) is False  # FR #818: flag alone is not enough
    assert gitclaim.is_repo_uat(_uat("#0")) is False
    assert gitclaim.is_repo_uat({"repo": REPO, "task": "MRB", "id": "#0", "repo_uat": True}) is False


def test_offer_focus_top_skips_per_pr_uat_even_with_repo_uat_flag(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _uat("#802", repo_uat=True, seq=1),  # poisoned legacy shape
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#10",
                    "line": "next",
                    "url": f"https://github.com/{REPO}/issues/10",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert (job.get("task"), job.get("id")) == ("FR", "#10")


def test_offer_top_skips_legacy_per_pr_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _uat("#813", seq=1),
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": "#11",
                    "line": "next",
                    "url": f"https://github.com/{REPO}/issues/11",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert (job.get("task"), job.get("id")) == ("FR", "#11")


def test_assign_row_refuses_per_pr_uat(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    import registered_machines

    registered_machines.save_registered(tmp_path, {"ionos", "marchhare"})
    home = _home(tmp_path)
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"ionos-11", "ionos-12"})
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_uat("#815", seq=1)],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, reason = gitclaim.assign_row(home, "ionos-11", REPO, "UAT", "#815")
    assert st == "refused"
    assert "per-repo" in str(reason).lower() or "per-PR" in str(reason) or "#0" in str(reason)


def test_assign_row_allows_repo_uat_zero(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    import registered_machines

    registered_machines.save_registered(tmp_path, {"ionos", "marchhare"})
    home = _home(tmp_path)
    monkeypatch.setattr(gitclaim, "live_seat_nicks", lambda h: {"ionos-11", "ionos-12"})
    monkeypatch.setattr(gitclaim, "worker_working_on", lambda h, n: "")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_uat("#0", repo_uat=True, seq=1, url=f"https://github.com/{REPO}")],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.assign_row(home, "ionos-12", REPO, "UAT", "#0")
    assert st == "ok"
    assert isinstance(job, dict)
    assert (job.get("task"), job.get("id")) == ("UAT", "#0")


def test_prune_drops_per_pr_uat_and_poisoned_repo_uat_flag(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _uat("#802", seq=1),
                _uat("#813", repo_uat=True, seq=2),  # flag without #0
                _uat("#0", repo_uat=True, seq=3, url=f"https://github.com/{REPO}"),
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    out = gitclaim.prune_unassignable_queue(home)
    assert out.get("ok") is True
    assert out.get("dropped") == 2
    left = gitclaim.load_unaccepted(home)
    assert len(left) == 1
    assert gitclaim.is_repo_uat(left[0]) is True
