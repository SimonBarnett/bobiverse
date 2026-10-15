"""FR #4316: LiveStateTouched / runner aborts must auto-file release-blocker (+ machine:any)."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb


def _mini_recipe(**kwargs) -> bb.BuildRecipe:
    suites = kwargs.pop(
        "suites",
        [bb.SuiteSpec(name="common", cmd="pytest -q", cwd=".", timeout=30)],
    )
    pack = kwargs.pop(
        "pack",
        {
            "cmd": "pack {{version}} {{out_dir}}",
            "artifacts": ["app-{{version}}.msi", "app-{{version}}.msi.sha256"],
        },
    )
    release = kwargs.pop(
        "release",
        {"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
    )
    return bb.BuildRecipe(
        machine=kwargs.pop("machine", "ionos"),
        baseline=kwargs.pop("baseline", "last_release_tag"),
        suites=suites,
        pack=pack,
        release=release,
        cache_dirs=kwargs.pop("cache_dirs", []),
        max_parallel_builds=1,
        channel="#bobiverse",
    )


def test_fr4316_livestate_touched_files_blocker_with_machine_any(tmp_path: Path):
    filer = bb.FakeGitHubFiler()

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        raise bb.LiveStateTouched(
            "step common@HEAD damaged live state: C:\\Users\\Administrator\\.bobiverse\\queue.json lost 8"
        )

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.0",
        "HEAD",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="win-mpre8vi4u6u",
        run_command_fn=run_fn,
        pack_fn=lambda **k: [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert len(report.blockers_filed) == 1
    filed = report.blockers_filed[0]
    assert filed["action"] == "created"
    assert filed["kind"] == "step_failure"
    assert "LiveStateTouched" in filed.get("test_id", "") or "LiveStateTouched" in str(
        filer.list_open_issues("SimonBarnett/bobiverse")[0]["title"]
    )
    labels = set(filer.list_open_issues("SimonBarnett/bobiverse")[0]["labels"])
    assert bb.RELEASE_BLOCKER_LABEL in labels
    assert bb.MACHINE_ANY_LABEL in labels
    assert any("LiveStateTouched" in e for e in report.errors)
    assert any("BUILD fail" in ln for ln in report.announce_lines)
    assert any(
        ("blocker=" in ln) or ("issues/" in ln) or (str(filed["number"]) in ln)
        for ln in report.announce_lines
    )


def test_fr4316_generic_runner_error_files_blocker(tmp_path: Path):
    filer = bb.FakeGitHubFiler()

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        raise RuntimeError("disk full while unpacking baseline")

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.0",
        "HEAD",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert len(report.blockers_filed) == 1
    labels = set(filer.list_open_issues("SimonBarnett/bobiverse")[0]["labels"])
    assert bb.RELEASE_BLOCKER_LABEL in labels
    assert bb.MACHINE_ANY_LABEL in labels
    assert any("RuntimeError" in e for e in report.errors)


def test_fr4316_livestate_dedupes_second_hit(tmp_path: Path):
    filer = bb.FakeGitHubFiler()

    def boom(*a, **k):
        raise bb.LiveStateTouched("step common@HEAD damaged live state: queue.json lost 8")

    recipe = _mini_recipe()
    kwargs = dict(
        repo_root=tmp_path,
        repo="SimonBarnett/bobiverse",
        version="1.0.0",
        ref="HEAD",
        recipe=recipe,
        filer=filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=boom,
        pack_fn=lambda **k: [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    r1 = bb.BuildRunner(**kwargs).run()
    r2 = bb.BuildRunner(**{**kwargs, "version": "1.0.1", "work_dir": tmp_path / "work2", "log_dir": tmp_path / "logs2"}).run()
    assert r1.blockers_filed[0]["action"] == "created"
    assert r2.blockers_filed[0]["action"] == "commented"
    assert r2.blockers_filed[0]["number"] == r1.blockers_filed[0]["number"]
    assert len(filer.list_open_issues("SimonBarnett/bobiverse")) == 1


def test_fr4316_file_blocker_or_dedupe_accepts_extra_labels():
    filer = bb.FakeGitHubFiler()
    failure = bb.classify_step_failure("guard:LiveStateTouched:common")
    filed = bb.file_blocker_or_dedupe(
        filer,
        repo="SimonBarnett/bobiverse",
        version="1.0.0",
        ref="HEAD",
        failure=failure,
        log_excerpt="queue.json lost 8",
        extra_labels=[bb.MACHINE_ANY_LABEL],
    )
    assert filed["action"] == "created"
    assert bb.MACHINE_ANY_LABEL in filed["labels"]
    assert filed.get("url")
