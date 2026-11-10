"""FR #1093 / #6407: agentic_fomprep#56 DEV1 hard pin retired; rows stay unpinned."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def test_issue_pin_without_title_body(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(
        tmp_path, {"marchhare", "ce-priority-dev1", "win-mpre8vi4u6u"}
    )
    assert (
        gitclaim.infer_require_machine(
            title="",
            body="",
            repo="SimonBarnett/agentic_fomprep",
            ident="#56",
        )
        == ""
    )
    row = {
        "repo": "SimonBarnett/agentic_fomprep",
        "task": "FR",
        "id": "#56",
        "title": "",
        "body": "",
        "labels": ["feature-request"],
    }
    assert gitclaim.row_require_machine(row) == ""
    assert not gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-15656")
    assert not gitclaim.row_blocked_for_machine(row, "marchhare-35600")
    assert not gitclaim.row_blocked_for_machine(row, "flamingo-1")


def test_offer_skips_win_mpre_even_when_row_unstamped(tmp_path, monkeypatch):
    """FR #6407: unpinned #56 is offerable to any live seat (including win-mpre)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(
        home, {"marchhare", "ce-priority-dev1", "ionos", "win-mpre8vi4u6u"}
    )
    digest = bobreport.empty_digest()
    for mid in ("marchhare", "ce-priority-dev1", "ionos", "win-mpre8vi4u6u"):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = {"1": {"state": "idle"}}
    bobreport.save_digest(home, digest)

    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#56",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/agentic_fomprep#56",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "win-mpre8vi4u6u-15656", "#win-mpre8vi4u6u")
    assert st == "ok" and job["id"] == "#56"
    assert gitclaim.row_require_machine(job) == ""


def test_hard_pin_wins_over_require_machine_any(tmp_path, monkeypatch):
    """FR #6407: #56 hard pin retired; operator any is not overwritten by DEV1."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(
        tmp_path, {"marchhare", "ce-priority-dev1", "win-mpre8vi4u6u"}
    )
    row = {
        "repo": "SimonBarnett/agentic_fomprep",
        "task": "FR",
        "id": "#56",
        "require_machine": "any",
        "title": "",
        "body": "",
        "labels": ["feature-request"],
    }
    assert gitclaim.row_require_machine(row) == ""
    assert not gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-15656")
    gitclaim._stamp_require_machine(row)
    assert row.get("require_machine") == "any"


def test_resync_restamps_already_queued_row(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"ce-priority-dev1", "win-mpre8vi4u6u"})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/agentic_fomprep",
                    "task": "FR",
                    "id": "#56",
                    "seq": 1,
                    "ts": "t",
                    "line": "old",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    def fetch(url: str):
        if "/pulls" in url:
            return []
        if "/issues" in url:
            return [
                {
                    "number": 56,
                    "title": "FR: WP0 live section 15 proof (shell compile/install on ce-priority-dev)",
                    "body": "PRIORITY_WP0_INSTANCE=ce-priority-dev",
                    "html_url": "https://github.com/SimonBarnett/agentic_fomprep/issues/56",
                    "labels": [{"name": "feature-request"}],
                    "user": {"login": "u"},
                    "pull_request": None,
                    "state": "open",
                }
            ]
        return []

    gitclaim.resync_from_github(home, ["SimonBarnett/agentic_fomprep"], fetch_json=fetch)
    rows = gitclaim.load_unaccepted(home)
    assert len(rows) == 1
    assert gitclaim.row_require_machine(rows[0]) == ""
    assert "WP0" in (rows[0].get("title") or "")
