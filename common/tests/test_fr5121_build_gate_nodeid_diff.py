"""FR #5121: build gate diffs failing pytest nodeids (suite-level red must not hide new fails)."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb


REF_LOG = """
===== test session starts =====
FAILED jeeves/tests/test_chair_commands_020.py::test_old_a - AssertionError
FAILED jeeves/tests/test_chair_commands_020.py::test_old_b - AssertionError
FAILED jeeves/tests/test_chair_commands_020.py::test_new_c - AssertionError
===== 3 failed, 10 passed =====
"""

BASE_LOG = """
===== test session starts =====
FAILED jeeves/tests/test_chair_commands_020.py::test_old_a - AssertionError
FAILED jeeves/tests/test_chair_commands_020.py::test_old_b - AssertionError
===== 2 failed, 11 passed =====
"""

IDENTICAL_LOG = BASE_LOG


def test_fr5121_parse_pytest_failed_nodeids():
    ids = bb.parse_pytest_failed_nodeids(REF_LOG)
    assert ids == {
        "jeeves/tests/test_chair_commands_020.py::test_old_a",
        "jeeves/tests/test_chair_commands_020.py::test_old_b",
        "jeeves/tests/test_chair_commands_020.py::test_new_c",
    }


def test_fr5121_new_failing_nodeids_set_diff():
    new = bb.new_failing_nodeids(REF_LOG, BASE_LOG)
    assert new == {"jeeves/tests/test_chair_commands_020.py::test_new_c"}
    assert bb.new_failing_nodeids(IDENTICAL_LOG, BASE_LOG) == set()


def test_fr5121_brand_new_test_file_counts_as_new():
    ref = "FAILED new/tests/test_brand.py::test_x - boom\n"
    base = "FAILED old/tests/test_old.py::test_y - boom\n"
    assert bb.new_failing_nodeids(ref, base) == {"new/tests/test_brand.py::test_x"}


def test_fr5121_append_pytest_nodeid():
    assert (
        bb.append_pytest_nodeid("pytest -q", "a/b.py::t")
        == "pytest -q a/b.py::t"
    )


def _mini_recipe() -> bb.BuildRecipe:
    return bb.BuildRecipe(
        machine="ionos",
        baseline="last_release_tag",
        suites=[bb.SuiteSpec(name="jeeves", cmd="pytest -q", cwd=".", timeout=30)],
        pack={
            "cmd": "pack {{version}} {{out_dir}}",
            "artifacts": ["app-{{version}}.msi"],
        },
        release={"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
        cache_dirs=[],
        max_parallel_builds=1,
        channel="#bobiverse",
    )


def test_fr5121_baseline_red_plus_new_failure_blocks(tmp_path: Path):
    """Baseline already red; one new FAILED nodeid must block pack/release."""
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []
    solo_cmds: list[str] = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline == "tip":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, REF_LOG, False, 0.01)
        if ref_or_baseline == "baseline":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, BASE_LOG, False, 0.01)
        if str(ref_or_baseline).endswith("-solo"):
            solo_cmds.append(str(cmd))
            # New test still fails on solo → new_regression
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "FAILED jeeves/tests/test_chair_commands_020.py::test_new_c\n", False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.6",
        "tip",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="win-mpre8vi4u6u",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert pack_calls == []
    assert report.blockers_filed
    assert report.blockers_filed[0]["kind"] == "new_regression"
    assert "test_new_c" in report.blockers_filed[0].get("test_id", "") or any(
        "test_new_c" in str(x) for x in report.blockers_filed
    )
    assert any("test_new_c" in c for c in solo_cmds)


def test_fr5121_identical_failing_set_does_not_block(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline in ("tip", "baseline"):
            return bb.SuiteRunResult(name, ref_or_baseline, 1, BASE_LOG, False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.6",
        "tip",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or ["app-1.0.6.msi"],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is True
    assert pack_calls
    assert report.blockers_filed == []


def test_fr5121_new_test_file_that_fails_blocks(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []
    ref = "FAILED brand/tests/test_new.py::test_z - boom\n"
    base = "ok\n"

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline == "tip":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, ref, False, 0.01)
        if ref_or_baseline == "baseline":
            return bb.SuiteRunResult(name, ref_or_baseline, 0, base, False, 0.01)
        if str(ref_or_baseline).endswith("-solo"):
            return bb.SuiteRunResult(name, ref_or_baseline, 1, ref, False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.6",
        "tip",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert pack_calls == []
    assert report.blockers_filed[0]["kind"] == "new_regression"


def test_mrb5122_error_nodeid_counts_as_fail():
    """Hostile: collection ERROR lines must enter the set (not FAILED-only)."""
    text = "ERROR jeeves/tests/test_broken.py::test_x - ImportError\n"
    assert bb.parse_pytest_failed_nodeids(text) == {"jeeves/tests/test_broken.py::test_x"}
    assert bb.new_failing_nodeids(text, "FAILED other.py::t - x\n") == {
        "jeeves/tests/test_broken.py::test_x"
    }


def test_mrb5122_unparseable_red_fail_closed(tmp_path: Path):
    """Hostile: red tip with no FAILED/ERROR nodeids must block pack (fail closed)."""
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline == "tip":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "boom no pytest lines\n", False, 0.01)
        if ref_or_baseline == "baseline":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, BASE_LOG, False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.6",
        "tip",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert pack_calls == []
    assert report.blockers_filed
    assert report.blockers_filed[0]["kind"] == "new_regression"


def test_mrb5122_error_nodeid_counts_as_fail():
    """Hostile: collection ERROR lines must enter the set (not FAILED-only)."""
    text = "ERROR jeeves/tests/test_broken.py::test_x - ImportError\n"
    assert bb.parse_pytest_failed_nodeids(text) == {"jeeves/tests/test_broken.py::test_x"}
    assert bb.new_failing_nodeids(text, "FAILED other.py::t - x\n") == {
        "jeeves/tests/test_broken.py::test_x"
    }


def test_mrb5122_unparseable_red_fail_closed(tmp_path: Path):
    """Hostile: red tip with no FAILED/ERROR nodeids must block pack (fail closed)."""
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline == "tip":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "boom no pytest lines\n", False, 0.01)
        if ref_or_baseline == "baseline":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, BASE_LOG, False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "1.0.6",
        "tip",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert pack_calls == []
    assert report.blockers_filed
    assert report.blockers_filed[0]["kind"] == "new_regression"