"""docs/mrb-4324 hostile pins for FR #4316 / PR #4324 LiveStateTouched auto-file."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
from repo_layout import ROOT

BUILD = (ROOT / "common" / "scripts" / "bobiverse_build.py").read_text(encoding="utf-8")
CLI = (ROOT / "common" / "scripts" / "run_bobiverse_build.py").read_text(encoding="utf-8")


def test_mrb4324_file_runner_abort_blocker_helper_present():
    assert "def file_runner_abort_blocker" in BUILD
    assert "MACHINE_ANY_LABEL" in BUILD
    assert 'extra_labels=[MACHINE_ANY_LABEL]' in BUILD.replace(" ", "") or (
        "extra_labels=[MACHINE_ANY_LABEL]" in BUILD
    )
    # LiveStateTouched path uses guard: prefix; other exceptions use runner:
    assert "guard:LiveStateTouched:" in BUILD
    assert "runner:" in BUILD


def test_mrb4324_buildrunner_suite_and_pack_catch_call_filer():
    assert "file_runner_abort_blocker" in BUILD
    # suite-loop and pack-step both call the helper (two call sites minimum beyond def)
    assert BUILD.count("file_runner_abort_blocker(") >= 3
    assert "pack-step LiveStateTouched" in BUILD or 'suite_name="pack"' in BUILD


def test_mrb4324_cli_outer_except_files_blocker():
    assert "file_runner_abort_blocker" in CLI
    # outer except must still file when filer exists
    i_exc = CLI.index("except Exception as exc:")
    chunk = CLI[i_exc : i_exc + 1200]
    assert "file_runner_abort_blocker" in chunk
    assert "blocker=" in chunk


def test_mrb4324_announce_includes_blocker_urls():
    assert 'blocker=" +' in BUILD or "blocker=" in BUILD
    assert "blockers_filed" in BUILD


def test_mrb4324_pack_livestate_files_blocker(tmp_path: Path):
    """Behavioural: LiveStateTouched during pack still auto-files + machine:any."""
    filer = bb.FakeGitHubFiler()
    calls = {"n": 0}

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        calls["n"] += 1
        if name == "pack":
            raise bb.LiveStateTouched("step pack@HEAD damaged live state: queue.json lost 1")
        # suite steps succeed
        return bb.SuiteRunResult(
            name=name,
            ref_or_baseline=ref_or_baseline or "HEAD",
            exit_code=0,
            stdout="ok",
            timed_out=False,
            duration_s=0.01,
        )

    recipe = bb.BuildRecipe(
        machine="ionos",
        baseline="last_release_tag",
        suites=[bb.SuiteSpec(name="common", cmd="pytest -q", cwd=".", timeout=30)],
        pack={
            "cmd": "pack {{version}} {{out_dir}}",
            "artifacts": ["app-{{version}}.msi"],
        },
        release={"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
        cache_dirs=[],
        max_parallel_builds=1,
        channel="#bobiverse",
    )
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.0",
        "HEAD",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=None,
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert any(b.get("action") in ("created", "commented") for b in report.blockers_filed)
    issues = filer.list_open_issues("SimonBarnett/bobiverse")
    assert issues
    labels = set(issues[0]["labels"])
    assert bb.RELEASE_BLOCKER_LABEL in labels
    assert bb.MACHINE_ANY_LABEL in labels
