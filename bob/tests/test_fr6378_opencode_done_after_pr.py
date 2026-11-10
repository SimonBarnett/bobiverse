"""FR #6378: OpenCode DONE right after gh pr create; outbox from current job worktree."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import bob_worker as bw


def test_fr6378_finish_prompt_forbids_ci_polling_and_orders_done():
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#6378",
        worktree=r"D:\ai\worktrees\bobiverse\fr-6378",
        outbox=r"D:\ai\worktrees\bobiverse\fr-6378\.bob\outbox.txt",
    )
    low = text.lower()
    assert "gh pr create" in low
    assert "done" in low
    assert "checks --watch" in low or "pr checks" in low or "poll" in low
    assert "never" in low and ("ci" in low or "check" in low or "watch" in low)
    # DONE must be immediate after create (no wait between).
    create_i = low.find("gh pr create")
    done_i = low.find("append done")
    if done_i < 0:
        done_i = low.find("done for")
    assert create_i >= 0 and done_i > create_i
    prompt = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "marchhare", "marchhare-1")
    plow = prompt.lower()
    assert "6378" in plow or "checks --watch" in plow or "never wait" in plow or "no ci" in plow


def test_fr6378_stamp_outbox_footer_rewrites_any_prior_path():
    stale = r"C:\Users\Administrator\.grok\bob-bridge\worktrees\bobiverse\fr-6360\.bob\outbox.txt"
    fresh = r"C:\Users\Administrator\.grok\bob-bridge\worktrees\bobiverse\fr-6376\.bob\outbox.txt"
    line = (
        "FROM jeeves #marchhare marchhare-1: FR SimonBarnett/bobiverse#6376 "
        f"https://github.com/SimonBarnett/bobiverse/issues/6376 [outbox: {stale}]"
    )
    out = bw.opencode_stamp_outbox_footer(line, fresh)
    assert f"[outbox: {fresh}]" in out
    assert "fr-6360" not in out
    # Missing footer -> append
    bare = "FROM jeeves #x x: FR o/r#1 https://github.com/o/r/issues/1"
    out2 = bw.opencode_stamp_outbox_footer(bare, fresh)
    assert out2.rstrip().endswith(f"[outbox: {fresh}]")


def test_fr6378_consecutive_jobs_get_own_outbox_footer(tmp_path: Path):
    """Two consecutive OpenCode jobs each stamp their own worktree outbox."""
    wt1 = tmp_path / "fr-6360"
    wt2 = tmp_path / "fr-6376"
    for wt in (wt1, wt2):
        (wt / ".bob").mkdir(parents=True)
        (wt / ".bob" / "outbox.txt").write_text("", encoding="utf-8")

    class FakeRelay:
        outbox_path = wt1 / ".bob" / "outbox.txt"

    class FakeWorker:
        kind = "opencode"
        machine = "marchhare"
        run_dir = tmp_path / "run"
        relay = FakeRelay()
        logs: list[str] = []
        inject_calls: list[str] = []

        def log(self, msg: str) -> None:
            self.logs.append(msg)

        def _inject_line(self, proc, line: str, **kwargs):
            # Call the real stamp path via a thin wrapper of the opencode branch.
            return True

    # Unit the stamp helper through sequential calls (acceptance: each job own path).
    line1 = (
        f"FROM jeeves #marchhare m: FR SimonBarnett/bobiverse#6360 "
        f"https://github.com/SimonBarnett/bobiverse/issues/6360 "
        f"[outbox: {wt1 / '.bob' / 'outbox.txt'}]"
    )
    line2 = (
        f"FROM jeeves #marchhare m: FR SimonBarnett/bobiverse#6376 "
        f"https://github.com/SimonBarnett/bobiverse/issues/6376 "
        f"[outbox: {wt1 / '.bob' / 'outbox.txt'}]"  # stale leftover
    )
    ob1 = str(wt1 / ".bob" / "outbox.txt")
    ob2 = str(wt2 / ".bob" / "outbox.txt")
    stamped1 = bw.opencode_stamp_outbox_footer(line1, ob1)
    stamped2 = bw.opencode_stamp_outbox_footer(line2, ob2)
    assert f"[outbox: {ob1}]" in stamped1
    assert f"[outbox: {ob2}]" in stamped2
    assert "fr-6360" not in stamped2.split("[outbox:")[1]


def test_fr6378_finish_decide_existing_pr_writes_done_not_giveup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(tmp_path))
    monkeypatch.setenv("BOB_OPENCODE_FINISH_RUN_MAX", "1")

    class FakeBored:
        _opencode_finish_attempt = 1
        ack_open = True

        def on_outbox(self, payload: str) -> None:
            self.last = payload

    class FakeWorker:
        kind = "opencode"
        machine = "marchhare"
        run_dir = tmp_path
        bored = FakeBored()
        _opencode_finish_snap = {
            "head": "aaa",
            "porcelain": "",
            "origin_head": "aaa",
            "has_pr": True,
            "ok": True,
        }
        _opencode_job_outbox = tmp_path / ".bob" / "outbox.txt"
        logs: list[str] = []
        posted = None
        cleaned = False

        def log(self, msg: str) -> None:
            self.logs.append(msg)

        def _opencode_finish_post_done(self, job_key: str, pr_url: str, **kw) -> None:
            self.posted = (job_key, pr_url, kw)

        def _opencode_job_end_cleanup(self, job=None) -> None:
            self.cleaned = True

    (tmp_path / ".bob").mkdir(parents=True, exist_ok=True)
    w = FakeWorker()
    w._opencode_finish_decide = bw.Supervisor._opencode_finish_decide.__get__(w, FakeWorker)

    monkeypatch.setattr(
        bw,
        "opencode_finish_progress_snapshot",
        lambda wt, **kw: {
            "head": "aaa",
            "porcelain": "",
            "origin_head": "aaa",
            "has_pr": True,
            "ok": True,
            "branch": "fr-6378",
            "pr_url": "https://github.com/SimonBarnett/bobiverse/pull/6377",
        },
    )
    monkeypatch.setattr(bw, "opencode_finish_progress_changed", lambda a, b: False)
    monkeypatch.setattr(
        bw,
        "opencode_finish_open_pr_url",
        lambda wt, key, **kw: "https://github.com/SimonBarnett/bobiverse/pull/6377",
    )
    monkeypatch.setattr(
        bw,
        "opencode_finish_auto_pr",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not auto-create")),
    )

    verdict = w._opencode_finish_decide("FR SimonBarnett/bobiverse#6376")
    assert verdict == "done"
    assert w.posted[1].endswith("/pull/6377")
    assert w.cleaned is True
    assert any("pr_opened_by=model" in m for m in w.logs)
    assert any("done_by=worker" in m for m in w.logs)


def test_fr6378_open_pr_url_from_gh_list(tmp_path: Path):
    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    def run(argv, **kwargs):
        if "--abbrev-ref" in argv:
            return _R(0, "fr-6376\n")
        if "pr" in argv and "list" in argv:
            return _R(
                0,
                '[{"url":"https://github.com/SimonBarnett/bobiverse/pull/6377","number":6377}]\n',
            )
        return _R(1, "")

    url = bw.opencode_finish_open_pr_url(
        tmp_path, "FR SimonBarnett/bobiverse#6376", run=run
    )
    assert url == "https://github.com/SimonBarnett/bobiverse/pull/6377"
