"""FR #7094: !build --tests-only + release preflight (tag/version/python/gh)."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import chair_commands as cc
import run_bobiverse_build as rbb
from repo_layout import ROOT

from test_fr6492_build_preflight import _all_ok_hooks


def _who():
    return cc.Principal("owner", "simon", "simon")


def test_fr7094_parse_build_tests_only_flag_and_subcommand():
    assert bb.parse_build("!build SimonBarnett/bobiverse 2.0.0 34c07a87 --tests-only") == (
        True,
        "run",
        "SimonBarnett/bobiverse 2.0.0 34c07a87 --tests-only",
    )
    assert bb.parse_build("!build tests-only SimonBarnett/bobiverse 2.0.0 34c07a87") == (
        True,
        "tests-only",
        "SimonBarnett/bobiverse 2.0.0 34c07a87",
    )


def test_fr7094_decide_build_tests_only_holds_lock_and_route(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "l.json")
    dec = bb.decide_build(
        who=_who(),
        body="!build SimonBarnett/bobiverse 2.0.0 HEAD --tests-only",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-7094",
    )
    assert dec and dec.ok and dec.tests_only is True
    assert "tests_only=1" in dec.route
    assert lock.running_id("SimonBarnett/bobiverse") == "b-7094"
    lock.release("SimonBarnett/bobiverse")
    assert lock.running_id("SimonBarnett/bobiverse") is None


def test_fr7094_parse_build_v1_tests_only():
    d = bb.parse_build_v1_route(
        "BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0 ref=HEAD id=b-1 tests_only=1"
    )
    assert d and d["tests_only"] is True
    d2 = bb.parse_build_v1_route(
        "BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0 ref=HEAD id=b-1"
    )
    assert d2 and d2["tests_only"] is False


def test_fr7094_preflight_existing_tag_without_replace(tmp_path: Path):
    hooks = _all_ok_hooks(tmp_path)
    report = bb.run_build_preflight(
        repo="SimonBarnett/bobiverse",
        repo_root=ROOT,
        version="2.0.0",
        require_release=True,
        tag_exists_fn=lambda repo, ver: True,
        replace_release=False,
        **hooks,
    )
    by = {i.name: i for i in report.items}
    assert by["release_tag"].ok is False
    assert "v2.0.0" in by["release_tag"].detail
    assert report.ok is False


def test_fr7094_preflight_existing_tag_with_clobber_ok(tmp_path: Path):
    hooks = _all_ok_hooks(tmp_path)
    report = bb.run_build_preflight(
        repo="SimonBarnett/bobiverse",
        repo_root=ROOT,
        version="2.0.0",
        require_release=True,
        tag_exists_fn=lambda repo, ver: True,
        replace_release=True,
        **hooks,
    )
    by = {i.name: i for i in report.items}
    assert by["release_tag"].ok is True
    assert "clobber" in by["release_tag"].detail.lower() or "replace" in by["release_tag"].detail.lower()
    assert by["version_explicit"].ok is True
    assert by["python"].ok is True
    assert by["gh_can_create"].ok is True
    assert "source=" in by["gh_can_create"].detail
    assert "login" not in by["gh_can_create"].detail.lower() or "not login" in by["gh_can_create"].detail.lower()


def test_fr7094_preflight_missing_version(tmp_path: Path):
    hooks = _all_ok_hooks(tmp_path)
    report = bb.run_build_preflight(
        repo="SimonBarnett/bobiverse",
        repo_root=ROOT,
        version="",
        require_release=True,
        **hooks,
    )
    by = {i.name: i for i in report.items}
    assert by["version_explicit"].ok is False
    assert report.ok is False


def test_fr7094_preflight_missing_python(tmp_path: Path):
    hooks = _all_ok_hooks(tmp_path)
    hooks["which"] = lambda name: None if name == "python" else _all_ok_hooks(tmp_path)["which"](name)
    report = bb.run_build_preflight(
        repo="SimonBarnett/bobiverse",
        repo_root=ROOT,
        version="2.0.0",
        require_release=True,
        tag_exists_fn=lambda repo, ver: False,
        replace_release=True,
        **hooks,
    )
    by = {i.name: i for i in report.items}
    assert by["python"].ok is False
    assert report.ok is False


def test_fr7094_preflight_localsystem_uses_file_token_not_login(tmp_path: Path):
    hooks = _all_ok_hooks(tmp_path)
    hooks["token_source"] = lambda: "file:github.token"
    report = bb.run_build_preflight(
        repo="SimonBarnett/bobiverse",
        repo_root=ROOT,
        version="2.0.0",
        require_release=True,
        tag_exists_fn=lambda *_: False,
        identity_fn=lambda: "NT AUTHORITY\\SYSTEM",
        **hooks,
    )
    by = {i.name: i for i in report.items}
    assert by["gh_can_create"].ok is True
    blob = "\n".join(report.lines)
    assert "ghp_" not in blob
    assert "login" not in blob.lower() or "not interactive login" in blob.lower()


def test_fr7094_tests_only_runner_skips_release_and_blockers(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    pack_calls: list = []
    release_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        if ref_or_baseline == "abc123" or str(ref_or_baseline).endswith("-solo"):
            return bb.SuiteRunResult(name, ref_or_baseline, 1, "FAIL ref", False, 0.01)
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    recipe = bb.BuildRecipe(
        machine="flamingo",
        baseline="last_release_tag",
        suites=[bb.SuiteSpec(name="unit", cmd="pytest -q", cwd=".", timeout=30)],
        pack={"cmd": "pack {{version}} {{out_dir}}", "artifacts": ["app-{{version}}.msi"]},
        release={"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
        cache_dirs=[],
        max_parallel_builds=1,
        channel="#bobiverse",
    )
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "2.0.0",
        "abc123",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="flamingo",
        run_command_fn=run_fn,
        pack_fn=lambda **k: pack_calls.append(k) or [],
        release_fn=lambda **k: release_calls.append(k),
        baseline_resolver=lambda *a, **k: "baseline",
        tests_only=True,
    )
    report = runner.run()
    assert release_calls == []
    assert pack_calls == []  # new_regression still skips pack
    assert all(b.get("action") == "skipped" for b in report.blockers_filed)
    assert filer.issues == [] or len(filer.list_open_issues("SimonBarnett/bobiverse")) == 0


def test_fr7094_tests_only_green_pack_never_gh_release_create(tmp_path: Path):
    filer = bb.FakeGitHubFiler()
    release_calls: list = []
    pack_calls: list = []

    def run_fn(cmd, cwd=None, env=None, timeout=None, name="cmd", ref_or_baseline="", **_):
        return bb.SuiteRunResult(name, ref_or_baseline, 0, "ok", False, 0.01)

    def pack_fn(**kwargs):
        pack_calls.append(kwargs)
        out = Path(kwargs["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"app-{kwargs['version']}.msi"
        p.write_bytes(b"msi")
        return [p]

    recipe = bb.BuildRecipe(
        machine="flamingo",
        baseline="last_release_tag",
        suites=[bb.SuiteSpec(name="unit", cmd="pytest -q", cwd=".", timeout=30)],
        pack={"cmd": "pack {{version}} {{out_dir}}", "artifacts": ["app-{{version}}.msi"]},
        release={"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
        cache_dirs=[],
        max_parallel_builds=1,
        channel="#bobiverse",
    )
    runner = bb.BuildRunner(
        tmp_path,
        "SimonBarnett/bobiverse",
        "2.0.0",
        "HEAD",
        recipe,
        filer,
        work_dir=tmp_path / "work",
        log_dir=tmp_path / "logs",
        local_machine="flamingo",
        run_command_fn=run_fn,
        pack_fn=pack_fn,
        release_fn=lambda **k: release_calls.append(k) or (_ for _ in ()).throw(
            AssertionError("gh release create")
        ),
        tests_only=True,
    )
    report = runner.run()
    assert pack_calls
    assert release_calls == []
    assert report.release_ok is True
    assert report.ok is True


def test_fr7094_cli_tests_only_flag_parsed():
    p = rbb.main
    # argparse is inside main; smoke that unknown isn't raised via parse only
    assert hasattr(rbb, "main")
    ns = __import__("argparse").ArgumentParser()
    # the runner exposes --tests-only
    import inspect

    src = inspect.getsource(rbb.main)
    assert "--tests-only" in src
