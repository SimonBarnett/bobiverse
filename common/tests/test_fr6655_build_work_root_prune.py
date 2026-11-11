"""FR #6655: build-work root free-space preflight + prune finished dirs."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import run_bobiverse_build as rbb
from repo_layout import ROOT


def test_fr6655_resolve_root_prefers_dir_env_then_alias():
    env = {
        "BOBIVERSE_BUILD_WORK_DIR": r"D:\build-work-dir",
        "BOBIVERSE_BUILD_WORK": r"D:\build-work-alias",
        "ProgramData": r"C:\ProgramData",
    }
    assert bb.resolve_build_work_root(env) == Path(r"D:\build-work-dir")
    env2 = {"BOBIVERSE_BUILD_WORK": r"E:\work", "ProgramData": r"C:\ProgramData"}
    assert bb.resolve_build_work_root(env2) == Path(r"E:\work")
    env3 = {"ProgramData": r"C:\ProgramData"}
    assert bb.resolve_build_work_root(env3) == Path(r"C:\ProgramData") / "Bobiverse" / "build-work"


def test_fr6655_preflight_refuses_low_free(tmp_path: Path):
    recipe = bb.load_recipe(ROOT)
    work = tmp_path / "work"
    report = bb.run_build_preflight(
        repo="SimonBarnett/bobiverse",
        repo_root=ROOT,
        env={"BOBIVERSE_PYTHON": "C:\\Python\\Python312\\python.exe", "PATH": "C:\\Windows"},
        which=lambda name: "C:\\x\\" + name,
        resolve_python=lambda env: "C:\\Python\\Python312\\python.exe",
        missing_imports=lambda: [],
        token_source=lambda: "env:GH_TOKEN",
        gh_auth=lambda: None,
        recipe_loader=lambda root: recipe,
        work_dir=work,
        mkdir=lambda p: Path(p).mkdir(parents=True, exist_ok=True),
        free_gb=lambda p: 1.2,
    )
    assert report.ok is False
    bad = [i for i in report.items if i.name == "work_dir_free"]
    assert bad and bad[0].ok is False
    assert "free_gb=1.20" in bad[0].detail
    assert "work_dir_free=missing" in "\n".join(report.lines)


def test_fr6655_prune_keeps_last_n_and_skips_active(tmp_path: Path):
    root = tmp_path / "build-work"
    root.mkdir()
    removed: list[str] = []

    def _mk(name: str, mtime: float) -> Path:
        p = root / name
        p.mkdir()
        (p / "progress.jsonl").write_text("x\n", encoding="utf-8")
        import os

        os.utime(p, (mtime, mtime))
        os.utime(p / "progress.jsonl", (mtime, mtime))
        return p

    # now ~ 1_700_000_000
    now = 1_700_000_000.0
    old = now - (7 * 3600)
    _mk("v-old-1", old - 30)
    _mk("v-old-2", old - 20)
    _mk("v-old-3", old - 10)
    _mk("v-keep-new", old - 5)
    _mk("v-keep-newer", old - 1)
    active = root / "v-active"
    active.mkdir()
    (active / "progress.jsonl").write_text("live\n", encoding="utf-8")
    # Recent heartbeat: still going
    import os

    os.utime(active, (now - 60, now - 60))
    os.utime(active / "progress.jsonl", (now - 60, now - 60))

    pruned = bb.prune_build_work_dirs(
        root,
        keep=2,
        active_names={"v-active"},
        idle_s=6 * 3600,
        now=now,
        remove=lambda p: removed.append(p.name) or p.rename(p.with_name(p.name + ".gone")),
    )
    assert set(removed) == {"v-old-1", "v-old-2", "v-old-3"}
    assert (root / "v-keep-new").is_dir()
    assert (root / "v-keep-newer").is_dir()
    assert (root / "v-active").is_dir()
    assert "v-active" not in removed
    assert len(pruned) == 3


def test_fr6655_prune_never_touches_active_name_even_if_idle(tmp_path: Path):
    root = tmp_path / "build-work"
    root.mkdir()
    victim = root / "running-job"
    victim.mkdir()
    (victim / "result.json").write_text("{}", encoding="utf-8")
    import os

    now = 1_700_000_000.0
    os.utime(victim, (now - 10_000, now - 10_000))
    removed: list[str] = []
    bb.prune_build_work_dirs(
        root,
        keep=0,
        active_names={"running-job"},
        idle_s=1,
        now=now,
        remove=lambda p: removed.append(p.name),
    )
    assert removed == []
    assert victim.is_dir()


def test_fr6655_rbb_resolve_delegates_to_bb():
    env = {"BOBIVERSE_BUILD_WORK": r"D:\x", "ProgramData": r"C:\ProgramData"}
    assert rbb.resolve_build_work_dir("9.9.9", env=env) == Path(r"D:\x") / "9.9.9"
