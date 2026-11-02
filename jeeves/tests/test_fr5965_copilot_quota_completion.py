"""FR #5965: Copilot quota failures, no fake MRB FAIL, completed verdict, live-task sweep."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import copilot_dispatch as cd
import gitclaim
import shop_listen
import stuck_job_sweep as sweep


REPO = "SimonBarnett/bobiverse"
NOW = 1_700_000_000.0


def _queue(home: Path, *, accepted=None, unaccepted=None):
    home.mkdir(parents=True, exist_ok=True)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": list(unaccepted or []),
            "accepted": list(accepted or []),
            "done": [],
        },
    )


def _accept_copilot(home: Path, *, task="MRB", ident="#5954", started=NOW):
    row = {
        "repo": REPO,
        "task": task,
        "id": ident,
        "nick": "copilot",
        "accepted_ts": started,
        "url": f"https://github.com/{REPO}/pull/{ident.lstrip('#')}",
        "title": "t",
    }
    _queue(home, accepted=[row])
    return row


def _track_job(
    home: Path,
    *,
    task="MRB",
    ident="#5954",
    started=NOW,
    task_id="t-quota",
    pr_url: str | None = None,
):
    job = {
        "repo": REPO,
        "task": task,
        "id": ident,
        "task_id": task_id,
        "started": started,
    }
    if pr_url:
        job["pr_url"] = pr_url
    elif str(task).upper() == "MRB":
        job["pr_url"] = f"https://github.com/{REPO}/pull/{ident.lstrip('#')}"
    jobs = {"jobs": [job]}
    (home / cd.JOBS_NAME).write_text(json.dumps(jobs) + "\n", encoding="utf-8")
    return jobs["jobs"][0]


def test_fr5965_is_exhausted_monthly_quota_message():
    assert cd.is_exhausted(
        {"message": "You have exceeded your monthly quota", "usage": {"type": "ai_credits"}}
    )
    assert cd.is_exhausted({"error": {"message": "exceeded your monthly quota"}})
    assert cd.is_exhausted({"status": 403, "message": "quota exceeded"})


def test_fr5965_quota_session_fail_exhausts_no_fake_mrb_fail(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    _accept_copilot(home)
    job = _track_job(home)
    announced: list[str] = []

    def fake_announce(*args) -> None:
        # bobreport.enqueue_chair_fleet_privmsg(home, line)
        announced.append(str(args[-1] if args else ""))

    monkeypatch.setattr(bobreport, "enqueue_chair_fleet_privmsg", fake_announce)

    def get(path: str):
        assert job["task_id"] in path
        return {
            "state": "failed",
            "sessions": [
                {
                    "error": {
                        "code": "usage",
                        "message": "You have exceeded your monthly quota",
                    }
                }
            ],
        }

    out = cd.handle_timeout_or_fail(
        home, job, now=NOW + 60, reason="timeout", get=get
    )
    assert out["status"] == "quota"
    assert not cd.has_allowance(home, now=NOW + 60)
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    un = doc["unaccepted"]
    assert len(un) == 1
    assert "copilot" not in str(un[0].get("giveup_seats") or "").lower()
    assert int(un[0].get("giveup_count") or 0) == 0
    backoff = cd.load_mrb_backoff(home)
    assert int(backoff.get("mrb_fast_giveups") or 0) == 0
    blob = "\n".join(announced).lower()
    assert "quota" in blob
    assert "done mrb" not in blob or "fail" not in blob.split("done mrb")[-1][:40]
    assert "done mrb" not in blob or " pass" not in blob
    assert not any("DONE MRB" in a and "FAIL" in a for a in announced)
    assert any("copilot paused: coding-agent quota exceeded" in a for a in announced)
    assert cd._load_jobs(home).get("jobs") == []


def test_fr5965_announce_complete_infra_not_mrb_verdict():
    line = cd.announce_complete(
        repo=REPO, task="MRB", ident="#9", result="", reason="timeout",
        pr_url=f"https://github.com/{REPO}/pull/9",
    )
    assert "FAIL" not in line
    assert "PASS" not in line
    assert "timeout" in line.lower()
    assert "copilot" in line.lower()
    pass_line = cd.announce_complete(
        repo=REPO, task="MRB", ident="#9", result="PASS",
        pr_url=f"https://github.com/{REPO}/pull/9",
    )
    assert "DONE MRB" in pass_line and "PASS" in pass_line


def test_fr5965_completed_mrb_pass_from_session(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    _accept_copilot(home)
    job = _track_job(home, task_id="t-pass")
    announced: list[str] = []
    monkeypatch.setattr(
        bobreport,
        "enqueue_chair_fleet_privmsg",
        lambda *args: announced.append(str(args[-1] if args else "")),
    )

    def get(path: str):
        if "/tasks/" in path:
            return {
                "state": "completed",
                "sessions": [
                    {"output": "MRB PASS\n## MRB board\n**Verdict:** PASS\n"},
                ],
            }
        raise AssertionError(path)

    out = cd.handle_timeout_or_fail(
        home, job, now=NOW + 90, reason="timeout", get=get
    )
    assert out["status"] == "complete"
    assert out.get("verdict") == "PASS"
    assert any("DONE MRB" in a and "PASS" in a for a in announced)
    doc = gitclaim.load_queue(home)
    assert not any(r.get("nick") == "copilot" for r in doc.get("accepted") or [])


def test_fr5965_completed_mrb_no_verdict_returns_to_seats(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    _accept_copilot(home)
    job = _track_job(home, task_id="t-empty")
    announced: list[str] = []
    monkeypatch.setattr(
        bobreport,
        "enqueue_chair_fleet_privmsg",
        lambda *args: announced.append(str(args[-1] if args else "")),
    )

    def get(path: str):
        if "/tasks/" in path:
            return {"state": "completed", "sessions": [{"output": "looks fine"}]}
        if "/pulls/" in path and "/comments" in path:
            return []
        if path.endswith("/pulls/5954") or "/pulls/5954?" in path:
            return {"number": 5954, "head": {"sha": "abc123"}}
        return []

    out = cd.handle_timeout_or_fail(
        home, job, now=NOW + 90, reason="timeout", get=get
    )
    assert out["status"] == "requeue"
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert len(doc["unaccepted"]) == 1
    assert "copilot" not in str(doc["unaccepted"][0].get("giveup_seats") or "").lower()
    assert not any("DONE MRB" in a and ("PASS" in a or "FAIL" in a) for a in announced)


def test_fr5965_stuck_sweep_keeps_live_copilot_task(tmp_path: Path):
    home = tmp_path / "digest"
    accepted_ts = NOW - (sweep.SILENT_ACCEPTED_S + 60)
    _accept_copilot(home, task="FR", ident="#5764", started=accepted_ts)
    _track_job(home, task="FR", ident="#5764", started=NOW - 60, task_id="live-1")
    report = sweep.run_stuck_sweep(
        home,
        now=NOW,
        live={"flamingo-1"},
        idle={"flamingo-1"},
        activity={},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 0
    doc = gitclaim.load_queue(home)
    assert any(
        str(r.get("nick") or "").lower() == "copilot" and str(r.get("id")).endswith("5764")
        for r in doc.get("accepted") or []
    )


def test_fr5965_pool_for_digest_shows_exhausted_not_unlimited(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir(parents=True, exist_ok=True)
    (home / cd.ALLOWANCE_NAME).write_text(
        json.dumps(
            {
                "unlimited": True,
                "state": "exhausted",
                "tasks_exhausted": True,
                "exhausted": True,
                "remaining": 0,
                "plan": "pro",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    pool = cd.pool_for_digest(home)
    assert pool["state"] in ("exhausted", "quota_exhausted", "failed")
    assert pool["unlimited"] is False


def test_fr5965_tick_splits_timeout_failed_quota(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir(parents=True, exist_ok=True)
    (home / cd.ALLOWANCE_NAME).write_text(
        json.dumps({"enabled": True, "remaining": 5, "state": "ok", "unlimited": True}),
        encoding="utf-8",
    )
    _accept_copilot(home, ident="#1")
    job = _track_job(home, ident="#1", task_id="t1", started=NOW - cd.TASK_TIMEOUT_S - 10)
    monkeypatch.setattr(bobreport, "enqueue_chair_fleet_privmsg", lambda *_a: None)

    def get(path: str):
        return {
            "state": "failed",
            "sessions": [{"error": {"message": "You have exceeded your monthly quota"}}],
        }

    out = cd.tick(home, now=NOW, get=get, post=lambda *_a, **_k: {"status": 201, "id": "x"})
    assert int(out.get("quota") or 0) == 1
    assert int(out.get("timed_out") or 0) == 0
    assert int(out.get("failed") or 0) == 0


def test_fr5965_completed_message_quota_text_not_exhaust(tmp_path, monkeypatch):
    """Completed session message mentioning quota must not mark fuel exhausted."""
    home = tmp_path / "digest"
    home.mkdir(parents=True, exist_ok=True)
    (home / cd.ALLOWANCE_NAME).write_text(
        json.dumps(
            {
                "enabled": True,
                "remaining": 5,
                "state": "ok",
                "unlimited": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _accept_copilot(home)
    job = _track_job(home, task_id="t-msg")
    announced: list[str] = []
    monkeypatch.setattr(
        bobreport,
        "enqueue_chair_fleet_privmsg",
        lambda *args: announced.append(str(args[-1] if args else "")),
    )

    def get(path: str):
        if "/tasks/" in path:
            return {
                "state": "completed",
                "message": "Note: monthly quota discussion in board",
                "sessions": [
                    {
                        "message": "quota exceeded last month; this review PASS",
                        "output": "## MRB board\n**Verdict:** PASS\n",
                    }
                ],
            }
        raise AssertionError(path)

    out = cd.handle_timeout_or_fail(
        home, job, now=NOW + 90, reason="timeout", get=get
    )
    assert out["status"] == "complete"
    assert out.get("verdict") == "PASS"
    assert cd.has_allowance(home, now=NOW + 90)
    assert any("DONE MRB" in a and "PASS" in a for a in announced)
    assert not any("copilot paused" in a for a in announced)


def test_fr5965_stuck_sweep_keeps_tracked_past_task_timeout(tmp_path: Path):
    """Tracked Copilot job past TASK_TIMEOUT_S stays held until dispatcher settles."""
    home = tmp_path / "digest"
    accepted_ts = NOW - (sweep.SILENT_ACCEPTED_S + 60)
    started = NOW - (cd.TASK_TIMEOUT_S + 120)
    _accept_copilot(home, task="FR", ident="#5764", started=accepted_ts)
    _track_job(home, task="FR", ident="#5764", started=started, task_id="late-1")
    report = sweep.run_stuck_sweep(
        home,
        now=NOW,
        live={"flamingo-1"},
        idle={"flamingo-1"},
        activity={},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 0
    doc = gitclaim.load_queue(home)
    assert any(
        str(r.get("nick") or "").lower() == "copilot" and str(r.get("id")).endswith("5764")
        for r in doc.get("accepted") or []
    )


def test_fr5965_complete_not_ok_skips_announce(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    _accept_copilot(home)
    job = _track_job(home, task_id="t-stale")
    announced: list[str] = []
    monkeypatch.setattr(
        bobreport,
        "enqueue_chair_fleet_privmsg",
        lambda *args: announced.append(str(args[-1] if args else "")),
    )

    def get(path: str):
        if "/tasks/" in path:
            return {
                "state": "completed",
                "sessions": [{"output": "## MRB board\n**Verdict:** PASS\n"}],
            }
        raise AssertionError(path)

    def fake_complete(*_a, **_k):
        return ("already_done", None)

    monkeypatch.setattr(shop_listen, "complete_job_by_ref", fake_complete)
    out = cd.handle_timeout_or_fail(
        home, job, now=NOW + 90, reason="timeout", get=get
    )
    assert out["status"] == "already_done"
    assert announced == []
