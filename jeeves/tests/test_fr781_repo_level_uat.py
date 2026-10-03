"""FR #781: port gh-Jeeves#239 — UAT is per REPO (#0), never per-PR.

Source (closed superseded): https://github.com/SimonBarnett/gh-Jeeves/pull/239
Also closes the originating gap bobiverse#768.
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


def test_is_mrb_fix_pr_title_shapes():
    assert gitclaim.is_mrb_fix_pr_title("fix(mrb-229): refuse cross-repo")
    assert gitclaim.is_mrb_fix_pr_title("mrb-229-fix: refuse cross-repo")
    assert not gitclaim.is_mrb_fix_pr_title("fix(bobiverse#247): never invent")
    assert not gitclaim.is_mrb_fix_pr_title("docs(mrb-229): note")


def test_merged_pr_webhook_does_not_enqueue_per_pr_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#229",
                    "line": "fix(bobiverse#247)",
                    "url": f"https://github.com/{REPO}/pull/229",
                }
            ],
            "accepted": [],
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
                "number": 229,
                "title": "fix(bobiverse#247): never invent MRB /pull/N",
                "html_url": f"https://github.com/{REPO}/pull/229",
                "body": "Closes SimonBarnett/bobiverse#247",
                "merged": True,
            },
        },
    )
    assert claim is not None and claim.task == "MRB" and claim.merged is True
    gitclaim.apply_queue_event(home, claim)
    q = gitclaim.load_queue(home)
    assert not any(str(r.get("task") or "").upper() == "UAT" for r in q["unaccepted"])
    assert not any(str(r.get("task") or "").upper() == "MRB" for r in q["unaccepted"])


def test_mrb_fix_pr_opened_does_not_enqueue_mrb():
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": REPO},
            "pull_request": {
                "number": 237,
                "title": "mrb-229-fix: refuse cross-repo MRB pull URLs",
                "html_url": f"https://github.com/{REPO}/pull/237",
                "body": "Refs #229",
                "merged": False,
            },
        },
    )
    assert claim is None


def test_offer_skips_legacy_per_pr_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#229",
                    "pr_id": "#229",
                    "line": "fix(bobiverse#247)",
                    "url": f"https://github.com/{REPO}/pull/229",
                    "seq": 1,
                },
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#10",
                    "line": "next",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/10",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok"
    assert job is not None
    assert (job.get("task"), job.get("id")) == ("FR", "#10")


def test_offer_repo_level_uat(tmp_path: Path):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "UAT",
                    "id": "#0",
                    "repo_uat": True,
                    "merged_prs": ["#229"],
                    "line": f"UAT {REPO}: all issues closed, all PRs merged",
                    "url": f"https://github.com/{REPO}",
                    "seq": 1,
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job is not None
    assert (job.get("task"), job.get("id")) == ("UAT", "#0")
    assert job.get("repo_uat") is True
    assert gitclaim.format_assign_line("marchhare-1", job).startswith(
        f"marchhare-1: UAT {REPO}#0 "
    )


# ------------------------------------------------------------ FR #821: harden UAT gates
def test_is_repo_uat_requires_id_zero_and_rejects_mrb_fix_title():
    """t853u / #821: repo_uat alone is not enough; id must be #0; mrb-fix titles never count."""
    assert gitclaim.is_repo_uat(
        {"task": "UAT", "id": "#0", "repo_uat": True, "line": f"UAT {REPO}: clear"}
    )
    # Wrong id even with repo_uat stamped (the #813 / #815 class).
    assert not gitclaim.is_repo_uat(
        {"task": "UAT", "id": "#813", "repo_uat": True, "line": "fix(mrb-802): …"}
    )
    assert not gitclaim.is_repo_uat(
        {"task": "UAT", "id": "#815", "repo_uat": True, "title": "mrb-798-fix: expand successors"}
    )
    # #0 without the flag is not offerable.
    assert not gitclaim.is_repo_uat({"task": "UAT", "id": "#0", "line": "x"})
    # #0 + flag but title looks like mrb-*-fix: refuse.
    assert not gitclaim.is_repo_uat(
        {
            "task": "UAT",
            "id": "#0",
            "repo_uat": True,
            "line": "fix(mrb-802): should never be repo UAT",
        }
    )


def test_offer_and_assign_refuse_non_zero_uat_even_with_repo_uat_flag(tmp_path: Path, monkeypatch):
    import registered_machines

    home = _home(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare"})
    bad = {
        "repo": REPO,
        "task": "UAT",
        "id": "#813",
        "repo_uat": True,
        "line": "fix(mrb-802): archive richer docs",
        "title": "fix(mrb-802): archive richer docs",
        "url": f"https://github.com/{REPO}/pull/813",
        "seq": 1,
    }
    good_fr = {
        "repo": REPO,
        "task": "FR",
        "id": "#10",
        "line": "next",
        "url": f"https://github.com/{REPO}/issues/10",
        "seq": 2,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [bad, good_fr], "accepted": [], "done": [], "workers": {}},
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and (job.get("task"), job.get("id")) == ("FR", "#10")
    # Re-queue: offer_focus_top stamped offered_to on the FR; offer_top needs a fresh pick.
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [dict(bad), dict(good_fr)], "accepted": [], "done": [], "workers": {}},
    )
    st2, job2 = gitclaim.offer_top(home, "marchhare-2", "#marchhare")
    assert st2 == "ok" and (job2.get("task"), job2.get("id")) == ("FR", "#10")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [dict(bad)], "accepted": [], "done": [], "workers": {}},
    )
    st3, why = gitclaim.assign_row(home, "marchhare-3", REPO, "UAT", "#813")
    assert st3 == "refused"
    assert "repo" in str(why).lower() or "uat" in str(why).lower() or "#0" in str(why)


def test_prune_drops_mrb_fix_titled_uat_and_non_zero_repo_uat(tmp_path: Path):
    home = _home(tmp_path)
    rows = [
        {
            "repo": REPO,
            "task": "UAT",
            "id": "#813",
            "repo_uat": True,
            "line": "fix(mrb-802)",
            "title": "fix(mrb-802)",
            "seq": 1,
        },
        {
            "repo": REPO,
            "task": "UAT",
            "id": "#815",
            "line": "mrb-798-fix: expand",
            "title": "mrb-798-fix: expand",
            "seq": 2,
        },
        {
            "repo": REPO,
            "task": "UAT",
            "id": "#0",
            "repo_uat": True,
            "line": f"UAT {REPO}: clear",
            "seq": 3,
        },
        {
            "repo": REPO,
            "task": "FR",
            "id": "#5",
            "line": "keep",
            "seq": 4,
        },
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )
    res = gitclaim.prune_unassignable_queue(home)
    assert res.get("ok") is True
    kept = gitclaim.load_unaccepted(home)
    assert sorted((r["task"], r["id"]) for r in kept) == [("FR", "#5"), ("UAT", "#0")]


def test_giveup_cooldown_blocks_reoffer_of_repo_uat(tmp_path: Path):
    """#821: after GIVEUP, do not re-offer until cooldown expires (row stamp)."""
    import time

    home = _home(tmp_path)
    until = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 600))
    row = {
        "repo": REPO,
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "line": f"UAT {REPO}: clear",
        "url": f"https://github.com/{REPO}",
        "seq": 1,
        "cooldown_until": until,
        "giveup_count": 1,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": [], "workers": {}},
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-9", "#marchhare", now=time.time())
    assert st == "empty" and job is None
