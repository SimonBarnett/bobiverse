"""FR #4025: BUILD WP2 runner — templates, BUILD v1, FakeGitHubFiler, BuildRunner."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
from repo_layout import ROOT


def _mini_recipe(**kwargs) -> bb.BuildRecipe:
    suites = kwargs.pop(
        "suites",
        [bb.SuiteSpec(name="unit", cmd="pytest -q", cwd=".", timeout=30)],
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
        cache_dirs=kwargs.pop("cache_dirs", ["third_party/nssm"]),
        max_parallel_builds=1,
        channel="#bobiverse",
    )


def test_fr4025_render_template():
    assert (
        bb.render_template(
            "v={{version}} out={{out_dir}} ref={{ref}}",
            version="0.1.99",
            out_dir=r"C:\out",
            ref="abc",
        )
        == r"v=0.1.99 out=C:\out ref=abc"
    )
    assert bb.render_template("keep {{missing}}", version="1") == "keep {{missing}}"


def test_fr4025_parse_build_v1_route():
    d = bb.parse_build_v1_route(
        "BUILD v1 repos=SimonBarnett/bobiverse,SimonBarnett/other version=0.1.40 ref=main"
    )
    assert d is not None
    assert d["repos"] == ["SimonBarnett/bobiverse", "SimonBarnett/other"]
    assert d["version"] == "0.1.40"
    assert d["ref"] == "main"
    assert bb.parse_build_v1_route("!build SimonBarnett/bobiverse 0.1.40") is None
    assert bb.parse_build_v1_route("") is None


def test_fr4025_is_recipe_build_machine_fold():
    assert bb.is_recipe_build_machine("ionos", "win-mpre8vi4u6u")
    assert bb.is_recipe_build_machine("win-mpre8vi4u6u", "ionos")
    assert bb.is_recipe_build_machine("ionos", "ionos")
    assert bb.is_recipe_build_machine("win-mpre8vi4u6u", "win-mpre8vi4u6u")
    assert not bb.is_recipe_build_machine("ionos", "flamingo")
    assert bb.fold_build_machine("ionos") == bb.fold_build_machine("win-mpre8vi4u6u")


def test_fr4025_fake_filer_create_then_dedupe_comment():
    filer = bb.FakeGitHubFiler()
    failure = bb.classify_failure("unit", ref_failed=True, baseline_failed=False)
    first = bb.file_blocker_or_dedupe(
        filer,
        repo="SimonBarnett/bobiverse",
        version="0.1.40",
        ref="abc",
        failure=failure,
        log_excerpt="boom",
    )
    assert first["action"] == "created"
    assert first["number"] == 1
    issues = filer.list_open_issues("SimonBarnett/bobiverse")
    assert len(issues) == 1
    labels = set(issues[0]["labels"])
    assert bb.FEATURE_REQUEST_LABEL in labels
    assert bb.RELEASE_BLOCKER_LABEL in labels
    second = bb.file_blocker_or_dedupe(
        filer,
        repo="SimonBarnett/bobiverse",
        version="0.1.41",
        ref="def",
        failure=failure,
        log_excerpt="boom again",
    )
    assert second["action"] == "commented"
    assert second["number"] == 1
    assert len(filer.list_open_issues("SimonBarnett/bobiverse")) == 1
    assert len(filer.comments) == 1


def test_fr4025_build_runner_new_regression_skips_pack(tmp_path: Path):
    """Pack/release only when no new_regression/step_failure."""
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []
    release_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        # Fail only at the job ref; baseline passes.
        if ref_or_baseline == "abc123":
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "FAIL ref", False, 0.01)
        if str(ref_or_baseline).endswith("-solo"):
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "FAIL solo", False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    def pack_fn(**kwargs):
        pack_calls.append(kwargs)
        return []

    def release_fn(**kwargs):
        release_calls.append(kwargs)

    recipe = _mini_recipe()
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "0.1.40",
        "abc123",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="win-mpre8vi4u6u",
        run_command_fn=run_fn,
        pack_fn=pack_fn,
        release_fn=release_fn,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is False
    assert pack_calls == []
    assert release_calls == []
    assert len(report.blockers_filed) == 1
    assert report.blockers_filed[0]["action"] == "created"
    assert report.blockers_filed[0]["kind"] == "new_regression"
    assert any("BUILD fail" in ln for ln in report.announce_lines)


def test_fr4025_timeout_files_step_failure(tmp_path: Path):
    filer = bb.FakeGitHubFiler()

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        return bb.SuiteRunResult(name, ref_or_baseline, -1, "hung", True, float(timeout or 1))

    recipe = _mini_recipe()
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "0.1.40",
        "main",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
        run_command_fn=run_fn,
        pack_fn=lambda **k: (_ for _ in ()).throw(AssertionError("pack")),
        release_fn=lambda **k: (_ for _ in ()).throw(AssertionError("release")),
    )
    report = runner.run()
    assert report.ok is False
    assert report.blockers_filed
    assert report.blockers_filed[0]["kind"] == "step_failure"
    assert report.blockers_filed[0]["action"] == "created"


def test_fr4025_green_path_pack_and_prerelease(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []
    release_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    def pack_fn(**kwargs):
        pack_calls.append(kwargs)
        out = Path(kwargs["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        ver = kwargs["version"]
        assets = []
        for name in (f"app-{ver}.msi", f"app-{ver}.msi.sha256"):
            path = out / name
            path.write_text("stub\n", encoding="utf-8")
            assets.append(path)
        return assets

    def release_fn(**kwargs):
        release_calls.append(kwargs)

    recipe = _mini_recipe()
    assert recipe.release.get("never_latest") is True
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "0.1.40",
        "main",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="win-mpre8vi4u6u",
        run_command_fn=run_fn,
        pack_fn=pack_fn,
        release_fn=release_fn,
        baseline_resolver=lambda *a, **k: "baseline",
    )
    report = runner.run()
    assert report.ok is True
    assert report.pack_ok is True
    assert report.release_ok is True
    assert report.blockers_filed == []
    assert len(pack_calls) == 1
    assert pack_calls[0]["version"] == "0.1.40"
    assert "0.1.40" in pack_calls[0]["cmd"]
    assert len(release_calls) == 1
    assert release_calls[0]["prerelease"] is True
    assert release_calls[0]["latest"] is False
    assert release_calls[0]["tag"] == "v0.1.40"
    assert report.log_zip and Path(report.log_zip).is_file()
    assert any("BUILD ok" in ln for ln in report.announce_lines)
    # cache_dirs created under work_dir/cache
    assert (tmp_path / "work" / "cache" / "third_party" / "nssm").is_dir()


def test_fr4025_never_latest_pinned_from_recipe():
    recipe = bb.load_recipe(ROOT)
    assert recipe.release.get("never_latest") is True
    assert recipe.release.get("target") == "github-prerelease"
    tag = bb.render_template(str(recipe.release.get("tag") or "v{{version}}"), version="0.1.40")
    assert tag == "v0.1.40"


def test_fr4025_consume_build_v1(tmp_path: Path):
    line = "BUILD v1 repos=SimonBarnett/bobiverse version=0.1.40 ref=main"
    assert bb.consume_build_v1(line, "flamingo", "ionos") is False
    q = tmp_path / "build-queue"
    assert bb.consume_build_v1(line, "win-mpre8vi4u6u", "ionos", queue_dir=q) is True
    jobs = list(q.glob("build-*.json"))
    assert len(jobs) == 1
    data = jobs[0].read_text(encoding="utf-8")
    assert "0.1.40" in data
    assert "SimonBarnett/bobiverse" in data


def test_fr4025_dry_run_path(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    recipe = _mini_recipe()
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "0.1.40",
        "main",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="ionos",
    )
    report = runner.run(dry_run=True)
    assert report.ok is True
    assert report.pack_ok is False
    assert any("suite" in ln.lower() or "classify" in ln.lower() for ln in report.announce_lines)


def test_fr4025_run_command_timeout_kill(tmp_path: Path):
    """Injectable runner: TimeoutExpired path marks timed_out and kills."""

    class FakeProc:
        def __init__(self):
            self.killed = False
            self.returncode = None

        def communicate(self, timeout=None):
            raise TimeoutError("slow")

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            self.returncode = -1
            return -1

    class FakeSp:
        PIPE = -1
        STDOUT = -2
        TimeoutExpired = TimeoutError

        def __init__(self):
            self.proc = FakeProc()

        def Popen(self, *a, **k):
            return self.proc

    sp = FakeSp()
    res = bb.run_command("sleep 999", cwd=tmp_path, timeout=0.1, runner=sp, name="slow")
    assert res.timed_out is True
    assert res.exit_code == -1
    assert sp.proc.killed is True
    assert "timed_out" in res.stdout


def test_fr4025_cli_drain_script_exists():
    p = ROOT / "common" / "scripts" / "run_bobiverse_build.py"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "BuildRunner" in text
    assert "--queue-dir" in text
    assert "FR #4025" in text


def test_fr4025_github_filer_uses_gh_runner():
    """Live GitHubFiler must call gh (not raise NotImplementedError)."""
    calls = []

    class _CP:
        def __init__(self, stdout="", returncode=0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def fake_run(argv, capture_output=True, text=True, check=False):
        calls.append(list(argv))
        if argv[1] == "issue" and argv[2] == "list":
            return _CP('[{"number":9,"title":"t","body":"b","labels":[{"name":"feature-request"}],"state":"open"}]')
        if argv[1] == "issue" and argv[2] == "create":
            return _CP("https://github.com/SimonBarnett/bobiverse/issues/42\n")
        if argv[1] == "issue" and argv[2] == "comment":
            return _CP("")
        return _CP("", 1)

    filer = bb.GitHubFiler(gh_runner=fake_run)
    issues = filer.list_open_issues("SimonBarnett/bobiverse")
    assert issues[0]["number"] == 9
    assert "feature-request" in issues[0]["labels"]
    created = filer.create_issue(
        "SimonBarnett/bobiverse",
        "release-blocker: x",
        "body",
        labels=["feature-request", "release-blocker"],
    )
    assert created["number"] == 42
    filer.comment("SimonBarnett/bobiverse", 9, "note")
    assert any(c[2] == "list" for c in calls)
    assert any(c[2] == "create" for c in calls)
    assert any(c[2] == "comment" for c in calls)
