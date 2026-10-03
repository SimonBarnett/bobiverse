"""FR #1093: stale queue rows must still pin agentic_fomprep#56 to ce-priority-dev1."""
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
        == "ce-priority-dev1"
    )
    row = {
        "repo": "SimonBarnett/agentic_fomprep",
        "task": "FR",
        "id": "#56",
        "title": "",
        "body": "",
        "labels": ["feature-request"],
    }
    assert gitclaim.row_require_machine(row) == "ce-priority-dev1"
    assert gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-15656")
    assert gitclaim.row_blocked_for_machine(row, "marchhare-35600")
    assert not gitclaim.row_blocked_for_machine(row, "ce-priority-dev1-1")


def test_offer_skips_win_mpre_even_when_row_unstamped(tmp_path, monkeypatch):
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
                    # Stale row: no title/body/require_machine (pre-#587 enqueue).
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, _job = gitclaim.offer_focus_top(home, "win-mpre8vi4u6u-15656", "#win-mpre8vi4u6u")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "ce-priority-dev1-1", "#ce-priority-dev1")
    assert st2 == "ok" and job2["id"] == "#56"
    assert job2.get("require_machine") == "ce-priority-dev1"


def test_hard_pin_wins_over_require_machine_any(tmp_path, monkeypatch):
    """Hostile MRB #1244: unpin token must not defeat agentic_fomprep#56 hard pin."""
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
    assert gitclaim.row_require_machine(row) == "ce-priority-dev1"
    assert gitclaim.row_blocked_for_machine(row, "win-mpre8vi4u6u-15656")
    gitclaim._stamp_require_machine(row)
    assert row.get("require_machine") == "ce-priority-dev1"


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
                    "title": "FR: WP0 live §15 proof (shell compile/install on ce-priority-dev)",
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
    assert rows[0]["require_machine"] == "ce-priority-dev1"
    assert "WP0" in (rows[0].get("title") or "")
