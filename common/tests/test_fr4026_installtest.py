"""FR #4026: BUILD WP3 INSTALL-TEST parse/decide/runner + CommandSpec."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import chair_commands as cc
from repo_layout import ROOT


def test_fr4026_validate_registry_includes_installtest():
    assert "installtest" in cc.COMMAND_BY_NAME
    assert cc.validate_registry() == []
    spec = cc.get_command("installtest")
    assert spec.roles == cc.OPS_ROLES
    assert "!installtest" in spec.syntax
    assert "dry-run" in spec.syntax
    assert "4026" in (spec.summary + " " + (spec.details or "")) or "4006" in (
        spec.summary + " " + (spec.details or "")
    )


def test_fr4026_help_ops_sees_installtest_worker_hides():
    ops = cc.Principal("owner", "simon", "simon")
    worker = cc.Principal("none", "box-1", "")
    assert cc.may("installtest", ops) is True
    assert cc.may("installtest", worker) is False
    idx = "\n".join(cc.build_help(ops))
    assert "!installtest" in idx
    idx_w = "\n".join(cc.build_help(worker))
    assert "!installtest" not in idx_w
    detail = "\n".join(cc.build_help(ops, "installtest"))
    assert "installtest" in detail.lower()
    assert "example:" in detail.lower() or "SimonBarnett" in detail


def test_fr4026_parse_installtest():
    assert bb.parse_installtest("hello") is None
    assert bb.parse_installtest("!installtest") == ("", "")
    sub, rest = bb.parse_installtest("!installtest dry-run SimonBarnett/bobiverse 0.1.32")
    assert sub == "dry-run"
    assert "SimonBarnett/bobiverse" in rest
    sub2, rest2 = bb.parse_installtest("!installtest SimonBarnett/bobiverse 0.1.32 v0.1.32")
    assert sub2 == "run"
    assert rest2.startswith("SimonBarnett/bobiverse")


def test_fr4026_decide_denied_for_worker():
    who = cc.Principal("none", "seat-1", "")
    dec = bb.decide_installtest(
        who=who,
        body="!installtest SimonBarnett/bobiverse 0.1.32",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        local_machine="win-mpre8vi4u6u",
    )
    assert dec and dec.ok is False and dec.reason == "denied"
    assert "denied" in dec.pm_lines[0]


def test_fr4026_decide_no_install_test(tmp_path: Path):
    who = cc.Principal("owner", "simon", "simon")
    recipe = bb.BuildRecipe(machine="ionos", suites=[bb.SuiteSpec("s", "echo")], install_test=None)

    def loader(_repo: str):
        return recipe

    dec = bb.decide_installtest(
        who=who,
        body="!installtest SimonBarnett/bobiverse 0.1.32",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader,
        local_machine="win-mpre8vi4u6u",
    )
    assert dec and dec.ok is False and dec.reason == "no_install_test"
    assert any("no install_test" in ln for ln in dec.pm_lines)


def test_fr4026_decide_dry_run_plan():
    who = cc.Principal("owner", "simon", "simon")
    dec = bb.decide_installtest(
        who=who,
        body="!installtest dry-run SimonBarnett/bobiverse 0.1.32 HEAD",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        local_machine="win-mpre8vi4u6u",
    )
    assert dec and dec.ok and dec.dry_run
    assert any("dry-run" in ln for ln in dec.pm_lines)
    assert "msiexec" in " ".join(dec.pm_lines).lower() or "post-check" in " ".join(dec.pm_lines).lower()
    assert dec.route == ""


def test_fr4026_machine_fold_ionos_matches_win_mpre():
    assert bb.is_recipe_build_machine("ionos", "win-mpre8vi4u6u")
    assert bb.is_recipe_build_machine("win-mpre8vi4u6u", "ionos")
    assert not bb.is_recipe_build_machine("ionos", "marchhare")
    who = cc.Principal("ear", "Bob-win-mpre8vi4u6u", "", "win-mpre8vi4u6u")
    dec = bb.decide_installtest(
        who=who,
        body="!installtest SimonBarnett/bobiverse 0.1.32",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        local_machine="win-mpre8vi4u6u",
    )
    assert dec and dec.ok and dec.route.startswith("INSTALLTEST v1")
    assert "ionos" in dec.machine or bb.fold_build_machine(dec.machine) == "win-mpre8vi4u6u"


def test_fr4026_decide_wrong_machine():
    who = cc.Principal("owner", "simon", "simon")
    dec = bb.decide_installtest(
        who=who,
        body="!installtest SimonBarnett/bobiverse 0.1.32",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        local_machine="marchhare",
    )
    assert dec and dec.ok is False and dec.reason == "wrong_machine"


def _green_postcheck(_product: str) -> dict:
    return {"service_up": True, "sasl_ok": True, "channels_ok": True, "seat_ack": True}


def test_fr4026_runner_green_path(tmp_path: Path):
    recipe = bb.load_recipe(ROOT)
    assert recipe.install_test
    msi_dir = tmp_path / "msi"
    msi_dir.mkdir()
    paths = []
    for prod in ("jeeves", "bob", "airc"):
        p = msi_dir / f"{prod}-0.1.99.msi"
        p.write_bytes(b"MZ-fake")
        paths.append(p)
    filer = bb.FakeGitHubFiler()
    calls = []

    def msiexec(msi, log):
        calls.append((Path(msi).name, Path(log).name))
        Path(log).write_text("msiexec ok\n", encoding="utf-8")
        return 0

    runner = bb.InstallTestRunner(
        repo="SimonBarnett/bobiverse",
        version="0.1.99",
        tag="v0.1.99",
        recipe=recipe,
        evidence_dir=tmp_path / "ev",
        msiexec_fn=msiexec,
        postcheck_fn=_green_postcheck,
        filer=filer,
        asset_resolver=lambda version, tag: paths,
    )
    report = runner.run()
    assert report.ok is True
    assert report.blockers_filed == []
    assert len(calls) == 3
    assert any("msiexec:jeeves:ok" in s for s in report.steps)
    assert any("postcheck:bob:ok" in s for s in report.steps)
    assert any("PASS" in a for a in report.announce_lines)
    zips = list((tmp_path).glob("**/installtest-0.1.99-evidence.zip"))
    assert zips, "evidence zip missing"


def test_fr4026_runner_msiexec_fail_files_blocker(tmp_path: Path):
    recipe = bb.load_recipe(ROOT)
    msi = tmp_path / "jeeves-0.1.99.msi"
    msi.write_bytes(b"MZ")
    recipe.install_test = dict(recipe.install_test or {})
    recipe.install_test["products"] = ["jeeves"]
    filer = bb.FakeGitHubFiler()

    def msiexec(msi_path, log):
        Path(log).write_text("msiexec failed\n", encoding="utf-8")
        return 1603

    runner = bb.InstallTestRunner(
        repo="SimonBarnett/bobiverse",
        version="0.1.99",
        recipe=recipe,
        evidence_dir=tmp_path / "ev",
        msiexec_fn=msiexec,
        postcheck_fn=_green_postcheck,
        filer=filer,
        asset_resolver=lambda v, t: [msi],
    )
    report = runner.run()
    assert report.ok is False
    issues = filer.list_open_issues("SimonBarnett/bobiverse")
    assert issues, "expected release-blocker issue"
    assert any("release-blocker" in (i.get("labels") or []) for i in issues)
    assert report.blockers_filed
    assert any("msiexec:jeeves:fail" in s for s in report.steps)


def test_fr4026_runner_postcheck_fail_files_blocker(tmp_path: Path):
    recipe = bb.load_recipe(ROOT)
    recipe.install_test = dict(recipe.install_test or {})
    recipe.install_test["products"] = ["bob"]
    msi = tmp_path / "bob-0.1.99.msi"
    msi.write_bytes(b"MZ")
    filer = bb.FakeGitHubFiler()

    def bad_post(_p):
        return {"service_up": True, "sasl_ok": False, "channels_ok": True, "seat_ack": True}

    def msiexec_ok(_m, log):
        Path(log).write_text("ok\n", encoding="utf-8")
        return 0

    runner = bb.InstallTestRunner(
        repo="SimonBarnett/bobiverse",
        version="0.1.99",
        recipe=recipe,
        evidence_dir=tmp_path / "ev",
        msiexec_fn=msiexec_ok,
        postcheck_fn=bad_post,
        filer=filer,
        asset_resolver=lambda v, t: [msi],
    )
    report = runner.run()
    assert report.ok is False
    issues = filer.list_open_issues("SimonBarnett/bobiverse")
    assert issues
    assert any(
        "postcheck:bob" in (i.get("title") or "") or "postcheck:bob" in (i.get("body") or "")
        for i in issues
    )


def test_fr4026_recipe_install_test_products():
    recipe = bb.load_recipe(ROOT)
    assert recipe.install_test
    assert recipe.install_test.get("machine") == "ionos"
    prods = recipe.install_test.get("products") or []
    assert set(prods) >= {"jeeves", "bob", "airc"}
