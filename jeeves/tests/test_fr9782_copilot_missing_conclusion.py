"""FR #9782: CCA missing_conclusion is infra soft-fail (free slot, no exhaust)."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import copilot_dispatch as cd
import gitclaim


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


def _accept_copilot(home: Path, *, task="FR", ident="#9749", started=NOW):
    row = {
        "repo": REPO,
        "task": task,
        "id": ident,
        "nick": "copilot",
        "accepted_ts": started,
        "url": f"https://github.com/{REPO}/issues/{ident.lstrip('#')}",
        "title": "t",
    }
    _queue(home, accepted=[row])
    return row


def _track_job(
    home: Path,
    *,
    task="FR",
    ident="#9749",
    started=NOW,
    task_id="t-missing",
):
    job = {
        "repo": REPO,
        "task": task,
        "id": ident,
        "task_id": task_id,
        "started": started,
    }
    jobs = {"jobs": [job]}
    (home / cd.JOBS_NAME).write_text(json.dumps(jobs) + "\n", encoding="utf-8")
    return jobs["jobs"][0]


def _enable_allowance(home: Path):
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


def test_fr9782_session_infra_soft_error_detects_missing_conclusion():
    info = {
        "state": "failed",
        "sessions": [
            {
                "error": {
                    "code": "missing_conclusion",
                    "message": "Workflow completed but conclusion is not available",
                }
            }
        ],
    }
    msg = cd.session_infra_soft_error(info)
    assert msg is not None
    assert "missing_conclusion" in msg.lower() or "conclusion" in msg.lower()
    assert cd.session_quota_error(info) is None


def test_fr9782_missing_conclusion_frees_slot_no_exhaust(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    _enable_allowance(home)
    _accept_copilot(home)
    job = _track_job(home)
    announced: list[str] = []
    monkeypatch.setattr(
        bobreport,
        "enqueue_chair_fleet_privmsg",
        lambda *args: announced.append(str(args[-1] if args else "")),
    )

    def get(path: str):
        assert job["task_id"] in path
        return {
            "state": "failed",
            "sessions": [
                {
                    "error": {
                        "code": "missing_conclusion",
                        "message": "Workflow completed but conclusion is not available",
                    }
                }
            ],
        }

    out = cd.handle_timeout_or_fail(
        home, job, now=NOW + 60, reason="timeout", get=get
    )
    assert out["status"] == "infra_retry"
    assert cd.has_allowance(home, now=NOW + 60)
    allow = cd.load_allowance(home)
    assert str(allow.get("state") or "").lower() not in (
        "exhausted",
        "quota_exhausted",
        "failed",
    )
    assert not allow.get("exhausted") and not allow.get("tasks_exhausted")
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    un = doc["unaccepted"]
    assert len(un) == 1
    assert "copilot" not in str(un[0].get("giveup_seats") or "").lower()
    assert int(un[0].get("giveup_count") or 0) == 0
    assert cd._load_jobs(home).get("jobs") == []
    # No quota pause chatter; optional infra note is fine.
    assert not any("copilot paused: coding-agent quota exceeded" in a for a in announced)
    # Surface for digest.copilot.tasks (#9748).
    surfaced = (
        str(allow.get("last_infra_error") or "") + " " + str(out.get("reason") or "")
    ).lower()
    assert "missing_conclusion" in surfaced or "conclusion" in surfaced


def test_fr9782_quota_still_exhausts(tmp_path, monkeypatch):
    """Fail-when guard: real quota must still stamp exhausted."""
    home = tmp_path / "digest"
    _enable_allowance(home)
    _accept_copilot(home, ident="#9750")
    job = _track_job(home, ident="#9750", task_id="t-quota")
    monkeypatch.setattr(bobreport, "enqueue_chair_fleet_privmsg", lambda *_a: None)

    def get(path: str):
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


def test_fr9782_tick_infra_retry_not_quota(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    _enable_allowance(home)
    _accept_copilot(home, ident="#9751")
    _track_job(
        home,
        ident="#9751",
        task_id="t-infra",
        started=NOW - cd.TASK_TIMEOUT_S - 10,
    )
    monkeypatch.setattr(bobreport, "enqueue_chair_fleet_privmsg", lambda *_a: None)

    def get(path: str):
        return {
            "state": "failed",
            "sessions": [
                {
                    "error": {
                        "code": "missing_conclusion",
                        "message": "Workflow completed but conclusion is not available",
                    }
                }
            ],
        }

    out = cd.tick(home, now=NOW, get=get, post=lambda *_a, **_k: {"status": 201, "id": "x"})
    assert int(out.get("quota") or 0) == 0
    assert int(out.get("infra_retry") or 0) == 1
    assert int(out.get("timed_out") or 0) == 0
    assert int(out.get("failed") or 0) == 0
    assert cd.has_allowance(home, now=NOW)
