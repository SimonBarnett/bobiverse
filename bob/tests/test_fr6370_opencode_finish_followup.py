"""FR #6370: OpenCode finish follow-up (push=progress, auto-PR, Temp cleanup)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import bob_worker as bw


def test_fr6370_finish_prompt_pins_body_and_no_temp():
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#6370",
        worktree=r"D:\Temp\bobiverse-fr-6370",
        outbox=r"D:\Temp\bobiverse-fr-6370\.bob\outbox.txt",
    )
    low = text.lower()
    assert "gh pr create" in low
    assert "--body" in low
    assert "%temp%" in low
    assert "never under" in low or "never" in low
    assert "external_directory" in low
    assert "worktree" in low
    prompt = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "marchhare", "marchhare-1")
    plow = prompt.lower()
    assert "6370" in plow or "--body" in plow
    assert "%temp%" in plow


def test_fr6370_progress_changed_on_origin_head_push():
    before = {
        "head": "aaa",
        "porcelain": "",
        "origin_head": "",
        "has_pr": False,
        "ok": True,
    }
    after_push = {
        "head": "aaa",
        "porcelain": "",
        "origin_head": "aaa",
        "has_pr": False,
        "ok": True,
    }
    assert bw.opencode_finish_progress_changed(before, after_push)
    after_pr = dict(after_push, has_pr=True)
    assert bw.opencode_finish_progress_changed(after_push, after_pr)
    assert not bw.opencode_finish_progress_changed(after_pr, after_pr)


def test_fr6370_progress_snapshot_uses_injectable_run():
    calls: list[list[str]] = []

    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    def run(argv, **kwargs):
        calls.append(list(argv))
        cmd = " ".join(argv)
        if "--abbrev-ref" in argv:
            return _R(0, "fr-6370\n")
        if "rev-parse" in argv and argv[-1] == "HEAD":
            return _R(0, "deadbeef\n")
        if "status" in argv:
            return _R(0, "")
        if argv[-1] == "origin/fr-6370":
            return _R(0, "deadbeef\n")
        if "pr" in argv and "list" in argv:
            return _R(0, "[]\n")
        return _R(1, "")

    # Need a real dir so is_dir() passes
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        snap = bw.opencode_finish_progress_snapshot(td, check_pr=True, run=run)
    assert snap["ok"] is True
    assert snap["head"] == "deadbeef"
    assert snap["branch"] == "fr-6370"
    assert snap["origin_head"] == "deadbeef"
    assert snap["has_pr"] is False
    assert any("gh" in c[0] for c in calls)


def test_fr6370_auto_pr_opens_when_ahead_no_pr(tmp_path: Path):
    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    created: list[list[str]] = []

    def run(argv, **kwargs):
        created.append(list(argv))
        if "--abbrev-ref" in argv:
            return _R(0, "fr-6370\n")
        if "rev-parse" in argv and argv[-1] == "HEAD":
            return _R(0, "abc123\n")
        if "status" in argv:
            return _R(0, "")
        if argv[-1] in ("origin/fr-6370", "@{u}"):
            return _R(0, "abc123\n")
        if "pr" in argv and "list" in argv:
            return _R(0, "[]\n")
        if "rev-list" in argv:
            return _R(0, "2\n")
        if "pr" in argv and "create" in argv:
            return _R(0, "https://github.com/SimonBarnett/bobiverse/pull/9999\n")
        return _R(1, "")

    url = bw.opencode_finish_auto_pr(
        tmp_path,
        "FR SimonBarnett/bobiverse#6370",
        run=run,
    )
    assert url == "https://github.com/SimonBarnett/bobiverse/pull/9999"
    body = tmp_path / ".bob" / "pr-body-auto.md"
    assert body.is_file()
    text = body.read_text(encoding="utf-8")
    assert "Closes SimonBarnett/bobiverse#6370" in text
    assert any("create" in a for a in created)


def test_fr6370_auto_pr_skips_when_has_pr(tmp_path: Path):
    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    def run(argv, **kwargs):
        if "--abbrev-ref" in argv:
            return _R(0, "fr-6370\n")
        if "rev-parse" in argv and argv[-1] == "HEAD":
            return _R(0, "abc\n")
        if "status" in argv:
            return _R(0, "")
        if argv[-1] in ("origin/fr-6370", "@{u}"):
            return _R(0, "abc\n")
        if "pr" in argv and "list" in argv:
            return _R(0, '[{"number":1}]\n')
        if "rev-list" in argv:
            return _R(0, "1\n")
        raise AssertionError(f"unexpected create: {argv}")

    url = bw.opencode_finish_auto_pr(
        tmp_path, "FR SimonBarnett/bobiverse#6370", run=run
    )
    assert url == ""


def test_fr6370_cleanup_removes_temp_extra_worktree(tmp_path: Path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    extra = tmp_path / "opencode" / "fr-extra"
    extra.mkdir(parents=True)
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))

    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    removed: list[str] = []
    pruned = {"n": 0}

    def run(argv, **kwargs):
        if "worktree" in argv and "list" in argv:
            porcelain = (
                f"worktree {job}\nHEAD abc\nbranch refs/heads/fr-6370\n\n"
                f"worktree {extra}\nHEAD def\nbranch refs/heads/detached\n\n"
            )
            return _R(0, porcelain)
        if "worktree" in argv and "remove" in argv:
            removed.append(argv[-1])
            return _R(0, "")
        if "worktree" in argv and "prune" in argv:
            pruned["n"] += 1
            return _R(0, "")
        return _R(1, "")

    out = bw.opencode_cleanup_extra_worktrees(job, temp_root=tmp_path, run=run)
    assert str(extra) in out or any(str(extra) in x for x in out)
    assert removed
    assert pruned["n"] == 1


def test_fr6370_finish_decide_auto_pr_returns_done(tmp_path: Path, monkeypatch):
    """After last attempt, pushed tip with no PR -> auto-PR + done (not giveup)."""
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(tmp_path))
    monkeypatch.setenv("BOB_OPENCODE_FINISH_RUN_MAX", "1")

    class FakeBored:
        _opencode_finish_attempt = 1

    class FakeWorker:
        kind = "opencode"
        machine = "flamingo"
        run_dir = tmp_path
        bored = FakeBored()
        _opencode_finish_snap = {
            "head": "aaa",
            "porcelain": "",
            "origin_head": "aaa",
            "has_pr": False,
            "ok": True,
        }
        logs: list[str] = []

        def log(self, msg: str) -> None:
            self.logs.append(msg)

        def _opencode_finish_post_done(self, job_key: str, pr_url: str) -> None:
            self.posted = (job_key, pr_url)

        def _opencode_job_end_cleanup(self, job=None) -> None:
            self.cleaned = True

    w = FakeWorker()
    # Bind real methods
    w._opencode_finish_decide = bw.Supervisor._opencode_finish_decide.__get__(w, FakeWorker)

    monkeypatch.setattr(
        bw,
        "opencode_finish_progress_snapshot",
        lambda wt, **kw: {
            "head": "aaa",
            "porcelain": "",
            "origin_head": "aaa",
            "has_pr": False,
            "ok": True,
            "branch": "fr-6370",
        },
    )
    monkeypatch.setattr(
        bw,
        "opencode_finish_progress_changed",
        lambda a, b: False,
    )
    monkeypatch.setattr(
        bw,
        "opencode_finish_auto_pr",
        lambda wt, key, **kw: "https://github.com/SimonBarnett/bobiverse/pull/42",
    )

    verdict = w._opencode_finish_decide("FR SimonBarnett/bobiverse#6370")
    assert verdict == "done"
    assert w.posted[1].endswith("/pull/42")
    assert w.cleaned is True


def test_fr6370_bored_emitter_done_verdict_no_giveup():
    from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait

    clock = FakeClock(0.0)
    e, _sent, logs = _emitter(
        clock, harvest_hold_s=90.0, done_miss_grace_s=5.0, ack_stale_s=2700.0
    )
    attempts: list[str] = []

    def _remind(key: str) -> None:
        attempts.append(key)

    def _decide(key: str) -> str:
        e.log(f"opencode finish-run key={key} attempt={len(attempts)}/1 progress=no")
        return "done"

    e.done_miss_remind_fn = _remind
    e.opencode_finish_decide_fn = _decide
    giveups: list[tuple[str, str]] = []
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))

    e.on_outbox("ACK FR SimonBarnett/bobiverse#6370")
    e.turn_ended(at=clock())
    clock.advance(6.0)
    assert _wait(lambda: e._done_miss_reminded, clock)  # noqa: SLF001
    assert len(attempts) == 1

    e.turn_ended(at=clock())
    assert _wait(
        lambda: any("finish auto-PR DONE" in m for m in logs),
        clock,
    ), logs
    assert not giveups
    assert e.ack_open is False
    e.stop()


def test_fr6370_parse_job_repo_issue():
    assert bw.opencode_parse_job_repo_issue("FR SimonBarnett/bobiverse#6370") == (
        "SimonBarnett/bobiverse",
        "6370",
    )
    assert bw.opencode_parse_job_repo_issue("hello") is None
