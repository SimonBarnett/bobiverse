"""FR #9416: do not auto-offer UAT for priority-mcp / priority-customer products.

Incident: after MRB #9413 DONE, offer_after_done handed UAT SimonBarnett/priority-mcp#0
to flamingo-19712. Operator cast-iron: no priority-customer UAT auto-offer.
PRODUCT_UAT_RELEASE remains title/tag metadata only — it must not grant offer.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import uat_release

NICK = "flamingo-19712"


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    # Clear FR #9382 synthetic allowlist pollution for this denial suite.
    monkeypatch.delenv(uat_release.UAT_RELEASE_REPOS_ENV, raising=False)
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo", "redqueen"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-11-23T18:35:00Z"},
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _uat_row(repo: str, **extra) -> dict:
    row = {
        "repo": repo,
        "task": "UAT",
        "id": "#0",
        "repo_uat": True,
        "line": f"UAT {repo}: clear",
        "url": f"https://github.com/{repo}",
        "seq": 1,
    }
    row.update(extra)
    return row


def test_priority_mcp_not_on_default_uat_release_allowlist():
    assert uat_release.repo_has_release_to_build("SimonBarnett/bobiverse")
    assert uat_release.repo_has_release_to_build("SimonBarnett/a-search")
    assert uat_release.repo_has_release_to_build("SimonBarnett/skills-visionary")
    assert not uat_release.repo_has_release_to_build("SimonBarnett/priority-mcp")
    assert not uat_release.repo_has_release_to_build("SimonBarnett/agentic_fomprep")
    # Title map may still name Priority Agent without granting offer.
    assert "simonbarnett/priority-mcp" in uat_release.PRODUCT_UAT_RELEASE
    assert "simonbarnett/priority-mcp" not in uat_release.DEFAULT_UAT_RELEASE_REPOS


def test_product_uat_release_keys_do_not_grant_offer():
    """FR #9416: PRODUCT_UAT_RELEASE is title/tag only."""
    for key in uat_release.PRODUCT_UAT_RELEASE:
        assert not uat_release.repo_has_release_to_build(key)


def test_offer_focus_top_purges_priority_mcp_uat(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _uat_row("SimonBarnett/priority-mcp"),
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#9416",
                    "line": "next",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/9416",
                    "seq": 2,
                },
            ],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    st, job = gitclaim.offer_focus_top(home, NICK, "#flamingo")
    assert st == "ok"
    assert job is not None
    assert job.get("task") == "FR"
    assert job.get("id") == "#9416"
    q = gitclaim.load_queue(home)
    assert not any(
        "priority-mcp" in str(r.get("repo") or "").lower()
        and str(r.get("task") or "").upper() == "UAT"
        for r in (q.get("unaccepted") or [])
    )


def test_assign_refuses_priority_mcp_uat(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_uat_row("SimonBarnett/priority-mcp")],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    st, why = gitclaim.assign_row(
        home, NICK, "SimonBarnett/priority-mcp", "UAT", "0"
    )
    assert st == "refused"
    assert why == uat_release.NO_RELEASE_TO_BUILD


def test_explicit_env_can_reenable_priority_mcp_uat(tmp_path: Path, monkeypatch):
    """Operator go: BOB_UAT_RELEASE_REPOS may re-add priority-mcp for a deliberate UAT."""
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setenv(
        uat_release.UAT_RELEASE_REPOS_ENV, "SimonBarnett/priority-mcp"
    )
    assert uat_release.repo_has_release_to_build(
        "SimonBarnett/priority-mcp", home=home
    )
    assert (
        gitclaim.uat_no_release_to_build_reason(
            _uat_row("SimonBarnett/priority-mcp"), home=home
        )
        is None
    )
