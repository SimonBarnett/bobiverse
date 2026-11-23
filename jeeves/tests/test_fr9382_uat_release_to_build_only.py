"""FR #9382: CAST IRON — offer/assign/enqueue UAT only for repos with a release to build."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import uat_release

NICK = "flamingo-14096"


def _home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": NICK, "state": "idle", "work": "", "updated": "2026-11-23T16:00:00Z"},
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


def test_uat_release_allowlist_includes_bobiverse_excludes_wetherby():
    assert uat_release.repo_has_release_to_build("SimonBarnett/bobiverse")
    assert uat_release.repo_has_release_to_build("SimonBarnett/priority-mcp")
    assert not uat_release.repo_has_release_to_build("SimonBarnett/wetherby")
    assert not uat_release.repo_has_release_to_build("SimonBarnett/obw")
    assert not uat_release.repo_has_release_to_build("SimonBarnett/ce-priority")


def test_uat_release_repos_file_and_env_extend(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    (home / uat_release.UAT_RELEASE_REPOS_FILE).write_text(
        "SimonBarnett/custom-product\n# comment\n", encoding="utf-8"
    )
    assert uat_release.repo_has_release_to_build(
        "SimonBarnett/custom-product", home=home
    )
    monkeypatch.setenv(uat_release.UAT_RELEASE_REPOS_ENV, "SimonBarnett/env-product")
    assert uat_release.repo_has_release_to_build("SimonBarnett/env-product", home=home)


def test_offer_focus_top_skips_and_purges_wetherby_uat(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _uat_row("SimonBarnett/wetherby"),
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
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    st, job = gitclaim.offer_focus_top(home, NICK, "#flamingo")
    assert st == "ok"
    assert job is not None
    assert job.get("task") == "FR"
    assert job.get("id") == "#10"
    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("repo") or "").lower() == "simonbarnett/wetherby"
        and str(r.get("task") or "").upper() == "UAT"
        for r in q["unaccepted"]
    )


def test_assign_row_refuses_no_release_to_build(tmp_path: Path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [_uat_row("SimonBarnett/wetherby")],
            "accepted": [],
            "done": [],
            "workers": {NICK: {"last_seen": 9e12}},
        },
    )
    st, why = gitclaim.assign_row(
        home, NICK, "SimonBarnett/wetherby", "UAT", "0"
    )
    assert st == "refused"
    assert why == uat_release.NO_RELEASE_TO_BUILD


def test_uat_no_release_reason_helper():
    assert (
        gitclaim.uat_no_release_to_build_reason(_uat_row("SimonBarnett/wetherby"))
        == "no-release-to-build"
    )
    assert (
        gitclaim.uat_no_release_to_build_reason(_uat_row("SimonBarnett/bobiverse"))
        is None
    )
