"""FR #5848: failed cloud reviews must not hide author-only MRB starvation."""
import json

import copilot_dispatch as cd
import focus_ignore
import gitclaim
import recycleseat
import stuck_job_sweep as sweep


REPO = "SimonBarnett/bobiverse"
AUTHOR = "flamingo-72904"
NOW = 1_800_000_000.0


def _setup(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    monkeypatch.setattr(cd, "is_high_priority", lambda *_: True)
    focus_ignore.handle_focus_cmd(home, f"high {REPO}")
    cd.set_allowance(home, remaining=100)
    rows = [
        {
            "repo": REPO, "task": "MRB", "id": f"#{n}",
            "title": "Review change", "author_seat": AUTHOR,
            "url": f"https://github.com/{REPO}/pull/{n}",
            "ts": cd._utc_iso(NOW), "seq": n,
        }
        for n in range(1, 5)
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": []},
    )
    return rows


def _fail_three(home, rows):
    for n, row in enumerate(rows[:3]):
        start = NOW + n * 60
        assert cd.dispatch_row(
            home, row, now=start, post=lambda *_: {"id": f"task-{n}"}
        )["status"] == "dispatched"
        job = cd._load_jobs(home)["jobs"][-1]
        assert cd.handle_timeout_or_fail(
            home, job, now=start + 40, reason="failed"
        )["status"] == "giveup"


def test_three_fast_giveups_back_off_fourth_and_report_all(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    _fail_three(tmp_path, rows)
    posts = []
    assert cd.tick(
        tmp_path, now=NOW + 180, post=lambda *args: posts.append(args)
    )["dispatched"] == 0
    assert posts == []
    lines = []
    report = sweep.run_stuck_sweep(
        tmp_path, now=NOW + 180, live={AUTHOR}, idle={AUTHOR},
        act=False, announce=lines.append,
    )
    assert len(report["stuck"]) == 4
    assert {r["rule"] for r in report["stuck"]} == {"no_eligible_reviewer"}
    assert any("no_eligible_reviewer" in line for line in sweep.format_stuck_lines(tmp_path))
    assert any("no_eligible_reviewer" in line for line in lines)


def test_backoff_expires_without_retrying_given_up_rows(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    _fail_three(tmp_path, rows)
    now = NOW + 160 + cd.MRB_BACKOFF_S
    posted = []
    out = cd.tick(tmp_path, now=now, post=lambda *a: posted.append(a) or {"id": "four"})
    assert out["dispatched"] == 1
    assert len(posted) == 1
    assert cd._load_jobs(tmp_path)["jobs"][-1]["id"] == "#4"


def test_mrb_disabled_does_not_disable_fr(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    doc = cd.load_allowance(tmp_path)
    doc["mrb"] = False
    (tmp_path / cd.ALLOWANCE_NAME).write_text(json.dumps(doc), encoding="utf-8")
    assert cd.dispatch_row(tmp_path, rows[0], now=NOW)["status"] == "skip"
    assert cd.should_dispatch(
        {**rows[0], "task": "FR"}, allowance=True, home=tmp_path, now=NOW
    )
    report = sweep.run_stuck_sweep(
        tmp_path, now=NOW, live={AUTHOR}, idle={AUTHOR}, act=False,
    )
    assert len(report["stuck"]) == 4


def test_successful_mrb_resets_fast_failure_streak(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    _fail_three(tmp_path, rows)
    # A valid verdict from an already accepted concurrent review ends backoff.
    import shop_listen
    shop_listen.accept_job_by_ref(
        tmp_path, nick="copilot", channel="#bobiverse",
        repo=REPO, task="MRB", ident="#4", title="Review change",
    )
    out = cd.handle_issue_comment(tmp_path, {
        "repository": {"full_name": REPO},
        "issue": {"number": 4, "pull_request": {}, "html_url": rows[3]["url"]},
        "comment": {"body": "MRB PASS\n**Verdict:** PASS",
                    "user": {"login": "copilot-swe-agent"}},
    })
    assert out["status"] == "ok"
    assert cd.mrb_dispatch_enabled(tmp_path, now=NOW + 180)
    assert cd.load_allowance(tmp_path)["mrb_fast_giveups"] == 0


def test_copilot_giveup_preserved_by_author_only_recycle(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    _fail_three(tmp_path, rows)
    install = tmp_path / "install"
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, live={AUTHOR, "copilot"}, idle={AUTHOR, "copilot"},
        install_root=install, now=NOW + 180,
    )
    assert any("author_only" in line and "recycle" in line for line in lines)
    requests = list(recycleseat.queue_dir(install).glob("req-*.json"))
    assert len(requests) == 1
    assert json.loads(requests[0].read_text())["nick"] == AUTHOR
    assert all(
        gitclaim.nick_in_giveup_seats(row, "copilot")
        for row in gitclaim.load_unaccepted(tmp_path) if row["id"] != "#4"
    )


def test_available_cloud_or_busy_human_reviewer_not_starved(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    report = sweep.run_stuck_sweep(
        tmp_path, now=NOW, live={AUTHOR}, idle={AUTHOR}, act=False,
    )
    assert report["stuck"] == []
    assert gitclaim.detect_mrb_reviewer_deadlock(
        tmp_path, rows=rows, live={AUTHOR}, idle={AUTHOR}, now=NOW,
    ) is None
    _fail_three(tmp_path, rows)
    report = sweep.run_stuck_sweep(
        tmp_path, now=NOW + 180, live={AUTHOR, "marchhare-2"},
        idle={AUTHOR}, act=False,
    )
    assert report["stuck"] == []


def test_row_and_ledger_giveup_block_cloud_reviewer(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    row = rows[0]
    gitclaim.ledger_note_event(
        tmp_path, "copilot", "GIVEUP", "MRB", REPO, "#1", job=row,
    )
    assert not cd.mrb_reviewer_available(tmp_path, row, now=NOW)
    assert not cd.mrb_reviewer_available(
        tmp_path, {**rows[1], "giveup_seats": "copilot"}, now=NOW,
    )
