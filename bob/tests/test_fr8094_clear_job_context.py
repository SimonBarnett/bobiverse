"""FR #8094: after GIVEUP/DONE/NACK clear per-job context; refuse stale reuse.

Acceptance:
- GIVEUP job A then offer job B => prompt/worktree/branch/outbox name B only.
- Deliberately stale worktree/outbox/prompt => NACK stale_job_context.
- OpenCode agent launches never --resume across jobs.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import bob_worker as bw
import opencode_seat_contract as osc
from test_fr2802_bored_on_turn_end import FakeClock, _emitter

KEY_A = "MRB SimonBarnett/bobiverse#8089"
KEY_B = "FR SimonBarnett/bobiverse#8091"


def test_fr8094_helpers_leaf_and_stale_reason():
    assert bw.job_key_issue_number(KEY_A) == "8089"
    assert bw.job_key_kind_leaf(KEY_A) == "mrb-8089"
    assert bw.job_key_kind_leaf(KEY_B) == "fr-8091"
    assert (
        bw.stale_job_context_reason(
            KEY_B,
            worktree=r"C:\wt\bobiverse\mrb-8089",
            outbox=r"C:\wt\bobiverse\mrb-8089\.bob\outbox.txt",
        )
        == "stale_job_context"
    )
    assert (
        bw.stale_job_context_reason(
            KEY_B,
            worktree=r"C:\wt\bobiverse\fr-8091",
            outbox=r"C:\wt\bobiverse\fr-8091\.bob\outbox.txt",
            text=f"FINISH {KEY_B} Closes SimonBarnett/bobiverse#8091 branch fr-8091",
            branch="fr-8091",
        )
        == ""
    )


def test_fr8094_clear_per_job_env_drops_worktree(monkeypatch):
    monkeypatch.setenv("BOB_JOB_WORKTREE", r"C:\wt\bobiverse\mrb-8089")
    bw.clear_per_job_env()
    assert not (os.environ.get("BOB_JOB_WORKTREE") or "").strip()


def test_fr8094_giveup_a_then_offer_b_context_names_only_b(tmp_path: Path, monkeypatch):
    base = tmp_path / "worktrees"
    wt_a = base / "bobiverse" / "mrb-8089"
    wt_b = base / "bobiverse" / "fr-8091"
    wt_a.mkdir(parents=True)
    wt_b.mkdir(parents=True)
    (wt_a / ".bob").mkdir()
    (wt_b / ".bob").mkdir()
    monkeypatch.setenv("BOB_JOB_WORKTREE_BASE", str(base))
    monkeypatch.setenv("BOB_JOB_WORKTREE", str(wt_a))

    cleaned: list[str | None] = []

    clock = FakeClock(time.time())
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, done_miss_grace_s=60.0)
    giveups: list[tuple[str, str]] = []
    e.failed_turn_retry_fn = lambda k: None
    e.seat_release_giveup_fn = lambda k, r: giveups.append((k, r))
    e.job_end_cleanup_fn = lambda j: cleaned.append(j)

    e.on_outbox("ACK " + KEY_A)
    err = dict(
        error=True,
        error_class="BrokenPipeError",
        error_line="EPIPE: broken pipe, write",
    )
    e.turn_ended(at=clock(), **err)  # retry
    e.turn_ended(at=clock(), **err)  # GIVEUP
    assert giveups and giveups[0][0] == KEY_A
    # FR #8094: seat-release GIVEUP must mark finished + run job_end_cleanup.
    deadline = time.time() + 2.0
    while time.time() < deadline and not cleaned:
        time.sleep(0.05)
    assert cleaned == [KEY_A], cleaned
    assert KEY_A in e._finished_job_keys

    # Simulate cleanup body (thread may have run stub only).
    bw.clear_per_job_env()
    assert not (os.environ.get("BOB_JOB_WORKTREE") or "").strip()

    line_b = (
        f"FROM jeeves #flamingo nick: {KEY_B} "
        f"https://github.com/SimonBarnett/bobiverse/issues/8091"
    )
    prepared = osc.prepare_opencode_wire(
        line_b,
        {"BOB_JOB_WORKTREE_BASE": str(base)},
    )
    assert prepared.get("state") == "project", prepared
    assert prepared.get("key") == KEY_B
    path = str(prepared.get("path") or "")
    assert "fr-8091" in path.replace("/", "\\").lower()
    assert "8089" not in path
    steps = bw.opencode_job_finish_steps(
        job_key=KEY_B,
        worktree=path,
        outbox=str(Path(path) / ".bob" / "outbox.txt"),
    )
    assert "8091" in steps
    assert "8089" not in steps
    assert "fr-8091" in steps
    assert bw.stale_job_context_reason(
        KEY_B,
        worktree=path,
        outbox=str(Path(path) / ".bob" / "outbox.txt"),
        text=steps,
        branch="fr-8091",
    ) == ""
    e.stop()


def test_fr8094_deliberate_stale_state_nacks_without_commit_cue():
    nack = bw.stale_job_context_nack_line(
        KEY_B,
        worktree=r"D:\ai\worktrees\bobiverse\mrb-8089",
        outbox=r"D:\ai\worktrees\bobiverse\mrb-8089\.bob\outbox.txt",
        text="FINISH MRB SimonBarnett/bobiverse#8089 Closes SimonBarnett/bobiverse#8089",
        branch="fr-8089",
    )
    assert nack.startswith("NACK FR SimonBarnett/bobiverse#8091 stale_job_context")
    # Nothing to commit: refuse is pre-turn.
    assert "commit" not in nack.lower()


def test_fr8094_opencode_agent_launch_forbids_resume(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(cwd),
        "standing prompt",
        "opencode.exe",
        run_dir,
    )
    joined = " ".join(spec.argv) + "\n" + "\n".join(spec.files.values())
    assert "--resume" not in joined
    assert " --continue" not in joined
    assert "-r " not in joined.replace("-File", " ")
