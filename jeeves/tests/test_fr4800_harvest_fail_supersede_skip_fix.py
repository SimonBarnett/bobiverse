"""FR #4800: harvest FAIL-supersede / CLOSED tips skip FIX enqueue."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import mrb_merge_on_green
import repo_layout
import shop_listen

REPO = "SimonBarnett/bobiverse"
SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SEAT = "flamingo-31916"
URL = f"https://github.com/{REPO}/pull/4797"
ROOT = Path(repo_layout.ROOT)


def test_skip_harvest_closed_fail_supersede_helper():
    assert mrb_merge_on_green.skip_mrb_fail_fix_for_harvest(
        title="lesson(harvest): BEL tip",
        labels=("harvest-lesson", "via-intake"),
        closed=True,
        merged=False,
        comments=[{"body": "Verdict: FAIL-superseded (CLOSED not-useful)"}],
    )
    assert mrb_merge_on_green.skip_mrb_fail_fix_for_harvest(
        title="lesson(harvest): x",
        labels=("harvest-lesson",),
        closed=True,
        merged=False,
        comments=[{"body": "MRB CLOSED - not-useful: anecdote"}],
    )
    # Open product FAIL still queues FIX (FR #4718).
    assert not mrb_merge_on_green.skip_mrb_fail_fix_for_harvest(
        title="fix: keep market off keywords",
        labels=(),
        closed=False,
        merged=False,
        comments=[{"body": f"MRB FAIL @ {SHA}"}],
    )
    # Open harvest with real FAIL @ sha (needs a product fix) still queues.
    assert not mrb_merge_on_green.skip_mrb_fail_fix_for_harvest(
        title="lesson(harvest): needs a real fix",
        labels=("harvest-lesson",),
        closed=False,
        merged=False,
        comments=[{"body": f"MRB FAIL @ {SHA}"}],
    )


def test_done_fail_closed_harvest_skips_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    (tmp_path / "registered-machines.json").write_text(
        '{"v":1,"machines":["flamingo"]}', encoding="utf-8"
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    doc = bobreport.empty_digest()
    doc["machines"]["flamingo"] = {
        "id": "flamingo",
        "online": True,
        "working_on": "",
        "worker_list": [{"nick": SEAT, "state": "idle", "work": ""}],
        "workers": {"31916": {"pid": "31916", "nick": SEAT, "state": "idle"}},
    }
    bobreport.save_digest(tmp_path, doc)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#4797",
                    "url": URL,
                    "nick": SEAT,
                    "title": "lesson(harvest): BEL tip",
                    "labels": ["harvest-lesson", "via-intake"],
                    "harvest_lesson": True,
                }
            ],
            "done": [],
        },
    )

    def fake_state(repo, num):
        return {
            "sha": SHA,
            "closed": True,
            "merged": False,
            "title": "lesson(harvest): BEL tip",
            "labels": ["harvest-lesson", "via-intake"],
            "comments": [
                {
                    "created_at": "2026-10-19T11:57:15Z",
                    "body": (
                        "## MRB board\n"
                        "**Verdict:** FAIL-superseded (CLOSED not-useful)"
                    ),
                }
            ],
        }

    monkeypatch.setattr(mrb_merge_on_green, "fetch_pr_state", fake_state)
    monkeypatch.setattr(
        mrb_merge_on_green, "head_sha_for_mrb_fail", lambda repo, num: SHA
    )
    result = shop_listen.handle_shop_worker_line(
        tmp_path,
        nick=SEAT,
        channel="#flamingo",
        body=f"DONE MRB {REPO}#4797 FAIL {URL}",
        post_fn=lambda _p: 204,
    )
    assert result.get("status") == "ok"
    assert result.get("mrb_fail_fix") == "skipped"
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(str(r.get("task") or "").upper() == "FIX" for r in rows)


def test_enqueue_mrb_fail_fix_skips_closed_harvest(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )

    def fake_state(repo, num):
        return {
            "sha": SHA,
            "closed": True,
            "merged": False,
            "title": "lesson(harvest): already covered",
            "labels": ["harvest-lesson"],
            "comments": [{"body": "FAIL-superseded citing product #4793"}],
        }

    monkeypatch.setattr(mrb_merge_on_green, "fetch_pr_state", fake_state)
    out = mrb_merge_on_green.enqueue_mrb_fail_fix(
        tmp_path, repo=REPO, pr="4797", sha=SHA, url=URL, nick=SEAT
    )
    assert out == "skipped"
    assert gitclaim.load_unaccepted(tmp_path) == []


def test_job_mrb_skill_pins_fr4800_done_pass():
    text = (
        ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #4800 (CAST IRON):" in text
    idx = text.index("FR #4800 (CAST IRON):")
    chunk = text[idx : idx + 700]
    assert "DONE MRB" in chunk and "PASS" in chunk
    assert "DONE FAIL" in chunk
    assert "4718" in chunk
    assert "FAIL-supersede" in chunk or "FAIL-superseded" in chunk
    assert "harvest" in chunk.lower()


def test_job_irc_skill_pins_fr4800():
    text = (
        ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #4800" in text
    idx = text.index("FR #4800")
    chunk = text[idx : idx + 700]
    assert "PASS" in chunk
