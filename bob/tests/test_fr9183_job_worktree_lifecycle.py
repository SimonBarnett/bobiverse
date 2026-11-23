"""FR #9183: finished-job worktree prune, locked retry, idle protect, disk-low guard."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import job_worktree_lifecycle as life


class FakeRun:
    def __init__(self, *, remove_code=0, remove_stderr="", prune_code=0):
        self.remove_code = remove_code
        self.remove_stderr = remove_stderr
        self.prune_code = prune_code
        self.calls: list[list[str]] = []

    def __call__(self, argv, capture_output=True, text=True, timeout=0):
        self.calls.append(list(argv))
        cmd = " ".join(argv)
        if "rev-parse" in cmd and "--git-common-dir" in cmd:
            return SimpleNamespace(returncode=0, stdout=".git\n", stderr="")
        if "worktree" in argv and "remove" in argv:
            return SimpleNamespace(
                returncode=self.remove_code, stdout="", stderr=self.remove_stderr
            )
        if "worktree" in argv and "prune" in argv:
            return SimpleNamespace(returncode=self.prune_code, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_min_free_default_is_five(monkeypatch):
    monkeypatch.delenv("BOB_JOB_WORKTREE_MIN_FREE_GB", raising=False)
    assert life.job_worktree_min_free_gb({}) == 5.0
    assert life.job_worktree_min_free_gb({"BOB_JOB_WORKTREE_MIN_FREE_GB": "7"}) == 7.0


def test_protected_paths_never_selected(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()
    keep = tmp_path / "keep-fr"
    keep.mkdir()
    assert life.is_protected_worktree_path(install, install_roots=[install])
    assert life.is_protected_worktree_path(keep, keep_paths=[keep])
    hot = tmp_path / "_hotpatch_watch" / "x"
    hot.mkdir(parents=True)
    assert life.is_protected_worktree_path(hot, install_roots=[install])
    victim = tmp_path / "fr-9183"
    victim.mkdir()
    assert not life.is_protected_worktree_path(
        victim, install_roots=[install], keep_paths=[keep]
    )


def test_remove_finished_after_done(tmp_path: Path):
    install = tmp_path / "install"
    install.mkdir()
    (install / ".git").mkdir()
    wt = tmp_path / "fr-1"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: ../install/.git/worktrees/fr-1\n", encoding="utf-8")
    fake = FakeRun()
    status = life.remove_finished_job_worktree(
        wt, install_root=install, run=fake, log_fn=lambda m: None
    )
    assert status == "ok"
    joined = [" ".join(c) for c in fake.calls]
    assert any("worktree remove --force" in j for j in joined)
    assert any("worktree prune" in j for j in joined)


def test_remove_on_giveup_and_nack_same_helper(tmp_path: Path):
    # DONE/GIVEUP/NACK all call the same remove helper — one behaviour.
    install = tmp_path / "install"
    install.mkdir()
    (install / ".git").mkdir()
    for name in ("fr-done", "fr-giveup", "fr-nack"):
        wt = tmp_path / name
        wt.mkdir()
        fake = FakeRun()
        assert (
            life.remove_finished_job_worktree(wt, install_root=install, run=fake)
            == "ok"
        )


def test_current_job_and_install_never_removed(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()
    (install / ".git").mkdir()
    current = tmp_path / "fr-current"
    current.mkdir()
    fake = FakeRun()
    assert (
        life.remove_finished_job_worktree(
            install, install_root=install, run=fake
        )
        == "skipped:protected"
    )
    assert (
        life.remove_finished_job_worktree(
            current,
            install_root=install,
            keep_paths=[current],
            run=fake,
        )
        == "skipped:protected"
    )
    assert fake.calls == [] or not any("remove" in c for c in [" ".join(x) for x in fake.calls])


def test_locked_worktree_queued_for_idle_retry(tmp_path: Path):
    life.clear_locked_worktree_queue_for_tests()
    install = tmp_path / "install"
    install.mkdir()
    (install / ".git").mkdir()
    wt = tmp_path / "fr-lock"
    wt.mkdir()
    fake = FakeRun(remove_code=1, remove_stderr="Access is denied: .pytest_cache")
    status = life.remove_finished_job_worktree(wt, install_root=install, run=fake)
    assert status == "retry:locked"
    assert str(wt) in life.pending_locked_worktrees() or str(wt.resolve()) in [
        str(Path(p)) for p in life.pending_locked_worktrees()
    ]
    # Idle drain retries; still locked => re-queue, no crash.
    fake2 = FakeRun(remove_code=1, remove_stderr="Access is denied")
    results = life.drain_locked_worktree_retries(install_root=install, run=fake2)
    assert results
    assert any("retry:locked" in r for r in results)


def test_disk_low_guard_nacks_and_files_one_intake(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_JOB_WORKTREE_MIN_FREE_GB", "10000")
    posts: list[dict] = []

    def post_intake(**kwargs):
        posts.append(kwargs)

    dest = tmp_path / "worktrees"
    dest.mkdir()
    nack = life.admit_job_worktree_disk(
        dest,
        job_key="FR SimonBarnett/bobiverse#9183",
        machine="flamingo",
        env={"BOB_JOB_WORKTREE_MIN_FREE_GB": "10000"},
        home=tmp_path / "home",
        post_intake=post_intake,
    )
    assert nack.startswith("NACK FR SimonBarnett/bobiverse#9183 disk-low")
    assert len(posts) == 1
    # Second call same day: still NACK, no second intake.
    nack2 = life.admit_job_worktree_disk(
        dest,
        job_key="FR SimonBarnett/bobiverse#9183",
        machine="flamingo",
        env={"BOB_JOB_WORKTREE_MIN_FREE_GB": "10000"},
        home=tmp_path / "home",
        post_intake=post_intake,
    )
    assert "disk-low" in nack2
    assert len(posts) == 1


def test_disk_low_sweep_can_clear_guard(tmp_path: Path, monkeypatch):
    dest = tmp_path / "wt"
    dest.mkdir()
    # First free read is low; after sweep, monkeypatch free_gb_for_path high.
    calls = {"n": 0}
    real_free = life.free_gb_for_path

    def fake_free(path):
        calls["n"] += 1
        if calls["n"] == 1:
            return 0.5
        return 50.0

    monkeypatch.setattr(life, "free_gb_for_path", fake_free)
    swept = {"ok": False}

    def sweep():
        swept["ok"] = True

    nack = life.admit_job_worktree_disk(
        dest,
        job_key="FR x/y#1",
        machine="marchhare",
        env={"BOB_JOB_WORKTREE_MIN_FREE_GB": "5"},
        sweep_fn=sweep,
        home=tmp_path / "home",
        post_intake=lambda **k: None,
    )
    assert nack == ""
    assert swept["ok"] is True
    monkeypatch.setattr(life, "free_gb_for_path", real_free)


def test_opencode_seat_contract_default_min_free_five():
    from pathlib import Path as P

    text = (P(__file__).resolve().parents[1] / "scripts" / "opencode_seat_contract.py").read_text(
        encoding="utf-8"
    )
    assert "FR #9183" in text
    assert "admit_job_worktree_disk" in text
    assert 'return False, "disk-low"' in text
    assert life.DEFAULT_MIN_FREE_GB == 5.0


def test_bob_worker_wires_prune_on_job_end():
    from pathlib import Path as P

    text = (P(__file__).resolve().parents[1] / "scripts" / "bob_worker.py").read_text(
        encoding="utf-8"
    )
    assert "job_worktree_lifecycle" in text
    assert "remove_finished_job_worktree" in text
    assert "drain_locked_worktree_retries" in text
    assert "idle_worktree_sweep_fn" in text
    assert "_prune_finished_job_worktree" in text
    assert "FR #9183" in text
