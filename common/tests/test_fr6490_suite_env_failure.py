"""FR #6490: suite command-not-found is environment failure; BOBIVERSE_PYTHON on PATH."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import bobiverse_build as bb


def _mini_recipe(cmd: str = "python -c \"import sys\"") -> bb.BuildRecipe:
    return bb.BuildRecipe(
        machine="flamingo",
        baseline="last_release_tag",
        suites=[bb.SuiteSpec(name="unit", cmd=cmd, cwd=".", timeout=30)],
        pack={"cmd": "", "artifacts": []},
        release={"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
        cache_dirs=[],
        max_parallel_builds=1,
        channel="#bobiverse",
    )


def test_fr6490_detect_command_not_found():
    msg = (
        "'python' is not recognized as an internal or external command,\n"
        "operable program or batch file.\n"
    )
    assert bb.is_command_not_found(msg, 9009) is True
    assert bb.is_command_not_found(msg, 1) is True
    assert bb.is_command_not_found("FAILED tests/test_x.py::t - assert 0", 1) is False
    assert bb.is_command_not_found("ok", 0) is False


def test_fr6490_command_not_found_no_blocker_comments(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        out = "'python' is not recognized as an internal or external command"
        return bb.SuiteRunResult(name, ref_or_baseline, 9009, out, False, 0.01)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "2.0.0",
        "HEAD",
        _mini_recipe(),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="flamingo",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert report.blockers_filed == []
    assert pack_calls == []
    assert filer.list_open_issues("SimonBarnett/bobiverse") == []
    assert filer.comments == []
    joined = "\n".join(report.errors + report.announce_lines)
    assert "environment" in joined.lower() or "not found" in joined.lower() or "python" in joined.lower()
    assert any("BUILD fail" in ln for ln in report.announce_lines)


def test_fr6490_real_regression_still_files_blocker(tmp_path: Path):
    filer = bb.FakeGitHubFiler()

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline == "abc123":
            return bb.SuiteRunResult(
                name, ref_or_baseline, 1, "FAILED tests/test_x.py::t - assert 0\n", False, 0.2
            )
        if str(ref_or_baseline).endswith("-solo"):
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "FAILED solo", False, 0.1)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.1)

    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "2.0.0",
        "abc123",
        _mini_recipe(cmd="pytest -q"),
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="flamingo",
        run_command_fn=run_fn,
        pack_fn=lambda **k: [],
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert len(report.blockers_filed) == 1
    assert report.blockers_filed[0]["kind"] == "new_regression"


def test_fr6490_prepend_bobiverse_python_to_path(tmp_path: Path, monkeypatch):
    fake_py = tmp_path / "py" / "python.exe"
    fake_py.parent.mkdir(parents=True)
    fake_py.write_text("", encoding="utf-8")
    (fake_py.parent / "Scripts").mkdir()
    monkeypatch.setenv("BOBIVERSE_PYTHON", str(fake_py))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    env = bb.suite_path_env_with_runner_python({})
    path = env.get("PATH") or ""
    parts = path.split(os.pathsep)
    assert str(fake_py.parent) == parts[0]
    assert str(fake_py.parent / "Scripts") == parts[1]


def test_fr6490_run_command_uses_bobiverse_python_on_path(tmp_path: Path, monkeypatch):
    """With BOBIVERSE_PYTHON set and no python on PATH, suite python -c still runs."""
    monkeypatch.setenv("BOBIVERSE_PYTHON", sys.executable)
    # Strip PATH down to something without python if possible — still prepend runner.
    monkeypatch.setenv("PATH", str(tmp_path / "no-python"))
    res = bb.run_command(
        'python -c "import sys; print(sys.executable)"',
        cwd=tmp_path,
        env={},
        timeout=30,
        name="unit",
        ref_or_baseline="HEAD",
    )
    assert res.exit_code == 0, res.stdout
    assert Path(sys.executable).name.lower() in res.stdout.lower() or str(Path(sys.executable)).lower() in res.stdout.lower()
