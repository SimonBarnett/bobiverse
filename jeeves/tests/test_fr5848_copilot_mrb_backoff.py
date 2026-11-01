"""FR #5848: failed cloud reviews must not hide author-only MRB starvation."""
import json

import copilot_dispatch as cd
import focus_ignore
import gitclaim
import recycleseat
import registered_machines
import stall_detectors
import stuck_job_sweep as sweep


REPO = "SimonBarnett/bobiverse"
AUTHOR = "flamingo-72904"
NOW = 1_800_000_000.0


def _setup(home, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
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
    assert cd.load_mrb_backoff(tmp_path)["mrb_fast_giveups"] == 0


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


def test_tick_keeps_review_input_pr_and_counts_real_fast_failures(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    for n, row in enumerate(rows[:3]):
        start = NOW + n * 60
        cd.dispatch_row(tmp_path, row, now=start, post=lambda *_: {"id": f"task-{n}"})
        before = cd.tick(
            tmp_path, now=start + 20, get=lambda *_: {"state": "running"},
        )
        assert before["released"] == 0
        assert gitclaim.load_accepted(tmp_path)[0]["id"] == row["id"]
        out = cd.tick(
            tmp_path, now=start + 40, get=lambda *_: {"state": "failed"},
        )
        assert out["timed_out"] == 1
    assert not cd.mrb_dispatch_enabled(tmp_path, now=NOW + 180)


def test_stall_path_respects_cloud_eligibility(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    snap = {"home": tmp_path, "now": NOW, "live": {AUTHOR},
            "idle": {AUTHOR}, "unaccepted": rows}
    assert stall_detectors.detect_self_review_deadlock(snap) == []
    _fail_three(tmp_path, rows)
    snap.update(now=NOW + 180, unaccepted=gitclaim.load_unaccepted(tmp_path))
    findings = stall_detectors.detect_self_review_deadlock(snap)
    assert len(findings) == 1
    assert findings[0]["id"] == "self-review-deadlock"


def test_expired_backoff_can_rearm_and_quota_refresh_preserves_it(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)
    _fail_three(tmp_path, rows)
    start = NOW + 160 + cd.MRB_BACKOFF_S
    for n in range(3):
        job = {"task": "MRB", "started": start + n * 60}
        cd._record_mrb_result(tmp_path, job, now=job["started"] + 40, giveup=True)
        assert cd.load_mrb_backoff(tmp_path)["mrb_fast_giveups"] == n + 1
    now = start + 180
    assert not cd.mrb_dispatch_enabled(tmp_path, now=now)
    cd.refresh_allowance(
        tmp_path, now=now,
        fetch_user=lambda: {"quota_snapshots": {"premium_interactions": {"unlimited": True}}},
    )
    assert cd.has_allowance(tmp_path, now=now)
    assert not cd.mrb_dispatch_enabled(tmp_path, now=now)


def test_non_fast_mrb_breaks_streak_but_fr_does_not(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    cd._record_mrb_result(tmp_path, {"task": "MRB", "started": NOW}, now=NOW + 40, giveup=True)
    cd._record_mrb_result(tmp_path, {"task": "FR", "started": NOW}, now=NOW + 50, giveup=True)
    assert cd.load_mrb_backoff(tmp_path)["mrb_fast_giveups"] == 1
    cd._record_mrb_result(tmp_path, {"task": "MRB", "started": NOW}, now=NOW + 121, giveup=True)
    assert cd.load_mrb_backoff(tmp_path)["mrb_fast_giveups"] == 0


def test_overlapping_quota_refresh_cannot_erase_backoff(tmp_path, monkeypatch):
    rows = _setup(tmp_path, monkeypatch)

    def fetch_user():
        _fail_three(tmp_path, rows)
        return {"quota_snapshots": {"premium_interactions": {"unlimited": True}}}

    cd.refresh_allowance(tmp_path, now=NOW + 180, fetch_user=fetch_user)
    assert cd.has_allowance(tmp_path, now=NOW + 180)
    assert not cd.mrb_dispatch_enabled(tmp_path, now=NOW + 180)


def test_bored_non_author_gets_mrb_despite_copilot_giveups(tmp_path, monkeypatch):
    import bobreport

    rows = _setup(tmp_path, monkeypatch)
    _fail_three(tmp_path, rows)
    nick = "flamingo-64124"
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": nick, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    status, row = gitclaim.offer_focus_top(
        tmp_path, nick, "#flamingo", now=NOW + 180,
        pr_exists=lambda *_args, **_kwargs: True,
    )
    assert status == "ok"
    assert row["id"] in {"#1", "#2", "#3"}
    assert row["offered_to"] == nick
