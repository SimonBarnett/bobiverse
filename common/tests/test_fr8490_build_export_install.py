"""FR #8490 slice D: pack export to catalog output + install/fleet fan-out."""
from __future__ import annotations

import json
from pathlib import Path

import bobiverse_build as bb
import builds_catalog as bc


def _mini_recipe(**kwargs) -> bb.BuildRecipe:
    suites = kwargs.pop(
        "suites",
        [bb.SuiteSpec(name="unit", cmd="pytest -q", cwd=".", timeout=30)],
    )
    pack = kwargs.pop(
        "pack",
        {
            "cmd": "pack {{version}} {{out_dir}}",
            "artifacts": ["app-{{version}}.msi"],
        },
    )
    release = kwargs.pop(
        "release",
        {"target": "github-prerelease", "tag": "v{{version}}", "never_latest": True},
    )
    install_test = kwargs.pop("install_test", None)
    return bb.BuildRecipe(
        machine=kwargs.pop("machine", "ionos"),
        baseline=kwargs.pop("baseline", "last_release_tag"),
        suites=suites,
        pack=pack,
        release=release,
        install_test=install_test,
        cache_dirs=kwargs.pop("cache_dirs", []),
        max_parallel_builds=1,
        channel="#bobiverse",
    )


def _pack_fn(**kwargs):
    out = Path(kwargs["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    ver = kwargs["version"]
    path = out / f"app-{ver}.msi"
    path.write_text("msi-stub\n", encoding="utf-8")
    return [path]


def test_export_pack_artifacts_copies_and_marker(tmp_path: Path):
    src = tmp_path / "out" / "bob-0.1.40.msi"
    src.parent.mkdir(parents=True)
    src.write_text("x", encoding="utf-8")
    dest_dir = tmp_path / "export"
    got = bb.export_pack_artifacts([src], dest_dir, version="0.1.40")
    assert len(got) == 1
    assert got[0].is_file()
    assert got[0].parent == dest_dir
    assert (dest_dir / "BUILD-EXPORT-0.1.40.txt").is_file()
    assert got[0].read_text(encoding="utf-8") == "x"


def test_resolve_install_plan_fleet_local_remote_offline():
    plan = bb.resolve_install_plan(
        "fleet",
        roster=["flamingo", "ionos", "walrus"],
        local_machine="ionos",
        live_machines=["ionos", "flamingo"],
    )
    assert plan["targets"] == ["flamingo", "ionos"]
    assert plan["skipped_offline"] == ["walrus"]
    assert plan["local"] == ["ionos"]
    assert plan["remote"] == ["flamingo"]

    single = bb.resolve_install_plan(
        "flamingo",
        roster=["flamingo", "ionos"],
        local_machine="ionos",
    )
    assert single["targets"] == ["flamingo"]
    assert single["local"] == []
    assert single["remote"] == ["flamingo"]


def test_enqueue_build_install_job_shape(tmp_path: Path):
    path = bb.enqueue_build_install_job(
        queue_dir=tmp_path / "iq",
        repo="SimonBarnett/bobiverse",
        version="0.1.40",
        tag="v0.1.40",
        machine="flamingo",
        output=r"D:\Temp\bobiverse-build",
        assets=[r"D:\Temp\bobiverse-build\bob-0.1.40.msi"],
    )
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "BUILD_INSTALL"
    assert data["machine"] == "flamingo"
    assert data["version"] == "0.1.40"
    assert data["output"].endswith("bobiverse-build")


def test_consume_build_v1_persists_output_install(tmp_path: Path):
    line = (
        "BUILD v1 repos=SimonBarnett/bobiverse version=0.1.40 ref=main id=b-1 "
        r"output=D:\Temp\bobiverse-build install=fleet"
    )
    q = tmp_path / "build-queue"
    assert bb.consume_build_v1(line, "ionos", "ionos", queue_dir=q) is True
    jobs = list(q.glob("build-*.json"))
    assert len(jobs) == 1
    data = json.loads(jobs[0].read_text(encoding="utf-8"))
    assert data["output"].replace("/", "\\").endswith("bobiverse-build")
    assert data["install"] == "fleet"


def test_runner_export_and_fleet_install(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOBIVERSE_DOWNLOAD_CACHE", raising=False)
    filer = bb.FakeGitHubFiler()
    export_dir = tmp_path / "catalog-out"
    install_q = tmp_path / "install-queue"
    local_calls: list = []

    def install_local(**kwargs):
        local_calls.append(kwargs)
        return {"ok": True, "machine": "ionos", "detail": ""}

    recipe = _mini_recipe(
        install_test={"machine": "ionos", "products": ["app"]},
    )
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
        run_command_fn=lambda *a, **k: bb.SuiteRunResult(
            k.get("name") or "cmd", k.get("ref_or_baseline") or "", 0, "ok", False, 0.01
        ),
        pack_fn=_pack_fn,
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
        output=str(export_dir),
        install="fleet",
        roster_machines=["ionos", "flamingo", "walrus"],
        live_machines=["ionos", "flamingo"],
        install_queue_dir=install_q,
        install_local_fn=install_local,
    )
    report = runner.run()
    assert report.pack_ok is True
    assert report.export_ok is True
    assert report.ok is True
    assert any(p.endswith("app-0.1.40.msi") for p in report.exported)
    assert (export_dir / "app-0.1.40.msi").is_file()
    assert "ionos" in report.install_targets
    assert "flamingo" in report.install_targets
    assert "walrus" not in report.install_targets
    assert local_calls, "local msiexec path should run for ionos"
    queued = list(install_q.glob("build-install-*.json"))
    assert len(queued) == 1
    qdata = json.loads(queued[0].read_text(encoding="utf-8"))
    assert qdata["machine"] == "flamingo"
    assert any("BUILD export" in ln for ln in report.announce_lines)
    assert any("BUILD install" in ln for ln in report.announce_lines)
    assert any("skipped=offline" in ln for ln in report.announce_lines)
    assert any("BUILD install queued" in ln for ln in report.announce_lines)


def test_runner_export_failure_blocks_ok(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOBIVERSE_DOWNLOAD_CACHE", raising=False)
    filer = bb.FakeGitHubFiler()

    def boom_export(*_a, **_k):
        raise OSError("disk full")

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
        run_command_fn=lambda *a, **k: bb.SuiteRunResult(
            "unit", "main", 0, "ok", False, 0.01
        ),
        pack_fn=_pack_fn,
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
        output=str(tmp_path / "out"),
        export_fn=boom_export,
    )
    report = runner.run()
    assert report.pack_ok is True
    assert report.export_ok is False
    assert report.ok is False
    assert any("BUILD export fail" in ln for ln in report.announce_lines)


def test_runner_install_without_install_test_warns(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOBIVERSE_DOWNLOAD_CACHE", raising=False)
    filer = bb.FakeGitHubFiler()
    recipe = _mini_recipe()  # no install_test
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
        run_command_fn=lambda *a, **k: bb.SuiteRunResult(
            "unit", "main", 0, "ok", False, 0.01
        ),
        pack_fn=_pack_fn,
        release_fn=lambda **k: None,
        baseline_resolver=lambda *a, **k: "baseline",
        output=str(tmp_path / "out"),
        install="ionos",
        roster_machines=["ionos"],
    )
    report = runner.run()
    assert report.ok is True  # pack+export ok; install WARN only
    assert report.export_ok is True
    assert report.install_ok is False
    assert any("skipped=no_install_test" in ln for ln in report.announce_lines)


def test_recipe_path_accepts_catalog_rel(tmp_path: Path):
    alt = tmp_path / "pack" / "build.yml"
    alt.parent.mkdir(parents=True)
    alt.write_text(
        "machine: ionos\nsuites:\n  - name: u\n    cmd: echo hi\n",
        encoding="utf-8",
    )
    assert bb.recipe_path(tmp_path, "pack/build.yml") == alt
    recipe = bb.load_recipe(tmp_path, "pack/build.yml")
    assert recipe.machine == "ionos"
    assert bb.recipe_path(tmp_path) == tmp_path / ".bobiverse" / "build.yml"


def test_expand_install_targets_matches_catalog_helper():
    roster = ["c", "a", "b"]
    assert bc.expand_install_targets("fleet", roster) == ["a", "b", "c"]
