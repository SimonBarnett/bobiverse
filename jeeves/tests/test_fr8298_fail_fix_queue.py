"""FR #8298: FAIL after nack leaves MRB; fr-N fix PRs are queued; no-terminal-reply expires."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import stuck_job_sweep


REPO = "SimonBarnett/bobiverse"


def _home(tmp_path: Path) -> Path:
    h = tmp_path / "chair"
    h.mkdir()
    gitclaim._write_queue(
        gitclaim.queue_path(h),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return h


def _pr(num: int, title: str, *, base: str, sha: str = "abc123", head: str | None = None) -> dict:
    return {
        "number": num,
        "title": title,
        "body": "",
        "draft": False,
        "html_url": f"https://github.com/{REPO}/pull/{num}",
        "user": {"login": "SimonBarnett"},
        "base": {"ref": base},
        "head": {"sha": sha, "ref": head or f"fr-{num}"},
    }


def _fetch(prs: list[dict]):
    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return prs
        if "/issues?" in url:
            return []
        return []

    return fetch


def _mrb_ids(home: Path) -> list:
    return [
        r.get("id")
        for r in gitclaim.load_unaccepted(home)
        if str(r.get("task") or "").upper() == "MRB"
    ]


def test_feature_base_fix_queued_while_parent_open(tmp_path, capsys):
    """Live #8260 bases on parent head fr-8234 (issue branch), not fr-8239."""
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(8239, "walrus jeeves irc", base="main", head="fr-8234"),
                _pr(8260, "fix(mrb-8239): pick up FAIL", base="fr-8234"),
            ]
        ),
    )
    ids = _mrb_ids(home)
    assert "#8260" in ids
    assert "#8239" in ids
    parent = next(r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#8239")
    assert "awaiting_fix_pr #8260" in str(parent.get("line") or "")
    err = capsys.readouterr().out
    assert "resync queue feature-base mrb-fix PR SimonBarnett/bobiverse#8260" in err


def test_feature_base_fr_pr_number_still_queues(tmp_path, capsys):
    """fr-<parent_pr_number> remains a valid feature-base match."""
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                _pr(8239, "walrus jeeves irc", base="main", head="fr-8239"),
                _pr(8260, "fix(mrb-8239): pick up FAIL", base="fr-8239"),
            ]
        ),
    )
    assert "#8260" in _mrb_ids(home)
    err = capsys.readouterr().out
    assert "resync queue feature-base mrb-fix PR SimonBarnett/bobiverse#8260" in err


def test_fail_after_nack_drops_parent_and_queues_fix(tmp_path, capsys):
    home = _home(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#8239",
                    "title": "walrus jeeves irc",
                    "url": f"https://github.com/{REPO}/pull/8239",
                    "giveup_seats": "flamingo-22648",
                    "giveup_reason": "no-terminal-reply",
                    "offer_outcomes": [
                        {
                            "seat": "flamingo-22648",
                            "outcome": "nack",
                            "reason": "no-terminal-reply",
                            "ts": "2026-11-18T17:45:41Z",
                        }
                    ],
                }
            ],
            "accepted": [],
            "done": [],
            "workers": {},
        },
    )
    parent = _pr(8239, "walrus jeeves irc", base="main", sha="6586df19", head="fr-8234")
    parent["comments"] = [
        {
            "body": "## MRB board\n**Verdict:** FAIL\n**MRB FAIL @ 6586df19**\n",
            "user": {"login": "redqueen"},
            "created_at": "2026-11-18T19:05:00Z",
        }
    ]
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch(
            [
                parent,
                _pr(8260, "fix(mrb-8239): pick up FAIL", base="fr-8234"),
            ]
        ),
    )
    ids = _mrb_ids(home)
    assert ids == ["#8260"]
    err = capsys.readouterr().out
    assert "resync offer FIX mrb-fail PR SimonBarnett/bobiverse#8239" in err


def test_merged_feature_fix_requeues_parent(tmp_path):
    """Once the fr-N fix is gone, the parent is an ordinary MRB again."""
    home = _home(tmp_path)
    gitclaim.resync_from_github(
        home,
        [REPO],
        fetch_json=_fetch([_pr(8239, "walrus jeeves irc", base="main", sha="newhead")]),
    )
    assert _mrb_ids(home) == ["#8239"]


def test_stuck_names_awaiting_fix_pr(tmp_path):
    home = _home(tmp_path)
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#8239",
        "title": "walrus jeeves irc",
        "url": f"https://github.com/{REPO}/pull/8239",
        "line": "awaiting_fix_pr #8260",
        "seq": 1,
        "added_ts": "2026-11-18T17:00:00Z",
    }
    out = stuck_job_sweep.classify_queue_row(
        row,
        bucket="unaccepted",
        home=home,
        live={"flamingo-4392"},
        idle=set(),
        now=1_700_000_000.0,
        ledger={},
    )
    assert out["rule"] == "awaiting_fix_pr #8260"
    assert out["stuck_reason"] == "awaiting_fix_pr #8260"


def test_no_terminal_reply_does_not_permanently_block():
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#8239",
        "giveup_seats": "flamingo-22648",
        "giveup_reason": "no-terminal-reply",
        "offer_outcomes": [
            {"seat": "flamingo-22648", "outcome": "nack", "reason": "no-terminal-reply"}
        ],
    }
    assert gitclaim.no_terminal_reply_does_not_block(row, "flamingo-22648")
    assert gitclaim._mrb_idle_block_reason(row, "flamingo-22648", {"flamingo-22648"}, {}) == ""
    gitclaim.stamp_seat_nack_cooldown(row, "flamingo-22648", now=__import__("time").time())
    assert (
        gitclaim._mrb_idle_block_reason(row, "flamingo-22648", {"flamingo-22648"}, {})
        == "nack-cooldown"
    )


def test_mixed_permanent_and_no_terminal_reply_keeps_permanent_blocked():
    """A later no-terminal-reply must not lift another seat's permanent give-up (MRB #8299).

    giveup_reason is row-level and overwritten by the latest GIVEUP, so a
    ``no-terminal-reply`` from one seat must not unblock a seat whose own
    offer_outcomes carry a permanent reason.
    """
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#8239",
        "giveup_seats": "flamingo-22648",
        "giveup_reason": "no-terminal-reply",
        "offer_outcomes": [
            {"seat": "flamingo-22648", "outcome": "nack", "reason": "self-mrb"},
            {"seat": "redqueen-7968", "outcome": "nack", "reason": "no-terminal-reply"},
        ],
    }
    assert not gitclaim.no_terminal_reply_does_not_block(row, "flamingo-22648")
    assert (
        gitclaim._mrb_idle_block_reason(row, "flamingo-22648", {"flamingo-22648"}, {})
        == "giveup"
    )
