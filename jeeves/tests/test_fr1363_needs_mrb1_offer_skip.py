"""FR #1363 legacy + operator 2026-10-04: needs-mrb1 must NOT block offers.

Also: BobCallback principal cues → ionos; GIVEUP stamps cooldown.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import gitclaim
import shop_listen


def _fr(repo: str, n: int, labels=None, title: str = "FR: x", body: str = ""):
    return {
        "repo": repo,
        "task": "FR",
        "id": f"#{n}",
        "seq": n,
        "ts": "t",
        "line": f"FR {repo}#{n}",
        "title": title,
        "body": body,
        "labels": list(labels or ["feature-request"]),
        "state": "open",
        "url": f"https://github.com/{repo}/issues/{n}",
    }


def test_needs_mrb1_stays_enqueueable_but_not_in_skip_fr():
    assert "needs-mrb1" not in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="FR: x", labels=("needs-mrb1", "via-intake")) is None
    # Operator 2026-10-04: label is a hallucination — never blocks offers.
    assert gitclaim.row_awaits_mrb1({"labels": ["feature-request", "needs-mrb1"]}) is False
    assert gitclaim.row_awaits_mrb1({"labels": ["feature-request"]}) is False


def test_offer_accepts_needs_mrb1_under_focus(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "focus.json").write_text(
        '{"v":1,"repos":["SimonBarnett/bobiverse"],"strict":true}',
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                _fr(
                    "SimonBarnett/bobiverse",
                    1316,
                    ["needs-mrb1", "feature-request", "via-intake"],
                    title="FR: plain ungated work with leftover needs-mrb1 label",
                ),
                _fr(
                    "SimonBarnett/bobiverse",
                    1363,
                    ["feature-request", "via-intake"],
                    title="chair re-offered FR after GIVEUP",
                ),
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "ok"
    assert job["id"] == "#1316"
    st2, job2 = gitclaim.offer_focus_top(home, "win-mpre8vi4u6u-15656", "#win-mpre8vi4u6u")
    assert st2 == "ok"
    assert job2["id"] == "#1363"


def test_bobcallback_principal_cues_require_ionos():
    title = "BobCallback task runs as SYSTEM against Administrator .bobiverse home"
    body = "Scheduled task BobCallback Principal SYSTEM while --home Admin .bobiverse"
    assert gitclaim.infer_require_machine(title=title, body=body) == "ionos"
    assert gitclaim.infer_require_machine(
        title="fix BobCallback principal vs home owner",
        body="re-register Interactive",
    ) == "ionos"
    # needs-mrb1 alone still must not become require_machine=mrb1
    assert gitclaim.infer_require_machine(labels=["needs-mrb1", "feature-request"]) in (None, "")


def test_bobcallback_row_blocks_marchhare(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    # seat_machine_ids() needs a roster so win-mpre8vi4u6u-<pid> parses (ionos fold).
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["win-mpre8vi4u6u","marchhare"]}',
        encoding="utf-8",
    )
    (home / "focus.json").write_text(
        '{"v":1,"repos":["SimonBarnett/bobiverse"],"strict":false}',
        encoding="utf-8",
    )
    row = _fr(
        "SimonBarnett/bobiverse",
        1316,
        ["feature-request", "via-intake"],
        title="BobCallback task runs as SYSTEM against Administrator .bobiverse home",
        body="Export-ScheduledTask BobCallback UserId S-1-5-18",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    # Clear roster cache after writing registry
    import bobreport

    bobreport._SEAT_ROSTER_CACHE["key"] = None
    st_mh, job_mh = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st_mh == "empty"
    assert job_mh is None
    st_io, job_io = gitclaim.offer_focus_top(home, "win-mpre8vi4u6u-15656", "#win-mpre8vi4u6u")
    assert st_io == "ok"
    assert job_io["id"] == "#1316"
    assert gitclaim.row_require_machine(job_io) == "ionos"


def test_giveup_stamps_cooldown_until(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    accepted = _fr("SimonBarnett/bobiverse", 99, ["feature-request"])
    accepted["nick"] = "marchhare-41928"
    accepted["accepted_ts"] = "t"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [accepted], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home, repo="SimonBarnett/bobiverse", task="FR", ident="#99"
    )
    assert st == "ok"
    assert job is not None
    assert job.get("cooldown_until")
    until = datetime.fromisoformat(str(job["cooldown_until"]).replace("Z", "+00:00")).timestamp()
    assert until > time.time()
    assert "marchhare-41928" in str(job.get("giveup_seats") or "")


def test_giveup_needs_mrb1_does_not_force_needs_human(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    accepted = _fr(
        "SimonBarnett/bobiverse",
        1316,
        ["needs-mrb1", "feature-request"],
        title="FR: leftover needs-mrb1 label",
    )
    accepted["nick"] = "win-mpre8vi4u6u-1"
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [accepted], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home, repo="SimonBarnett/bobiverse", task="FR", ident="#1316"
    )
    assert st == "ok"
    assert job.get("needs_human") is not True
    assert job.get("cooldown_until")
    # After cooldown window would pass — but same seat still on giveup_seats;
    # a different seat must be able to take it despite needs-mrb1 label.
    job.pop("cooldown_until", None)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [job], "accepted": [], "done": []},
    )
    (home / "focus.json").write_text('{"v":1,"repos":[],"strict":false}', encoding="utf-8")
    st2, job2 = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st2 == "ok"
    assert job2["id"] == "#1316"
