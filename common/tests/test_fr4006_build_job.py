"""FR #4006: BUILD job recipe, classify, dedupe, lock, !build decide/help."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import chair_commands as cc
from repo_layout import ROOT


def test_fr4006_validate_registry_includes_build():
    assert "build" in cc.COMMAND_BY_NAME
    assert cc.validate_registry() == []
    spec = cc.get_command("build")
    assert spec.roles == cc.OPS_ROLES
    assert "!build" in spec.syntax
    assert "dry-run" in spec.syntax
    assert "status" in spec.syntax
    assert "cancel" in spec.syntax


def test_fr4006_help_ops_sees_build_worker_hides():
    ops = cc.Principal("owner", "simon", "simon")
    worker = cc.Principal("none", "box-1", "")
    assert cc.may("build", ops) is True
    assert cc.may("build", worker) is False
    idx = "\n".join(cc.build_help(ops))
    assert "!build" in idx
    idx_w = "\n".join(cc.build_help(worker))
    assert "!build" not in idx_w
    detail = "\n".join(cc.build_help(ops, "build"))
    assert "owner/repo" in detail
    assert "bob" in detail.lower() or "simon" in detail.lower() or "ops" in detail.lower()
    assert "example:" in detail or "!build SimonBarnett" in detail


def test_fr4006_bobiverse_recipe_loads():
    recipe = bb.load_recipe(ROOT)
    assert recipe.machine == "ionos"
    assert len(recipe.suites) >= 4
    names = {s.name for s in recipe.suites}
    assert {"jeeves", "airc", "common", "bob"} <= names
    assert recipe.pack
    assert recipe.release.get("target") == "github-prerelease"
    assert recipe.release.get("never_latest") is True


def test_fr4006_no_recipe_refusal(tmp_path: Path):
    try:
        bb.load_recipe(tmp_path)
        assert False, "expected RecipeError"
    except bb.RecipeError as exc:
        assert "no .bobiverse/build.yml" in str(exc)


def test_fr4006_classify_new_preexisting_flaky():
    assert bb.classify_failure("t1", ref_failed=True, baseline_failed=False).kind == "new_regression"
    assert bb.classify_failure("t2", ref_failed=True, baseline_failed=True).kind == "pre_existing"
    assert bb.classify_failure("t3", ref_failed=True, baseline_failed=False, solo_passed=True).kind == "flaky"
    assert bb.classify_step_failure("pack").kind == "step_failure"


def test_fr4006_dedupe_comment_vs_new():
    open_issues = [
        {"number": 1, "title": "blocker t_foo", "body": "test: t_foo\ndedupe:deadbeef"},
    ]
    hit = bb.find_open_duplicate(open_issues, test_id="t_foo")
    assert hit and hit["number"] == 1
    miss = bb.find_open_duplicate(open_issues, test_id="t_other_unique")
    assert miss is None
    key = bb.issue_dedupe_key(test_id="t_foo")
    assert len(key) == 16


def test_fr4006_single_flight_lock(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json", max_parallel=1)
    ok, info = lock.try_acquire("SimonBarnett/bobiverse", "b1")
    assert ok and info == "b1"
    ok2, info2 = lock.try_acquire("SimonBarnett/bobiverse", "b2")
    assert not ok2 and info2 == "b1"
    # different repo blocked when max_parallel=1
    ok3, info3 = lock.try_acquire("SimonBarnett/other", "b3")
    assert not ok3 and "machine_busy" in info3
    lock.release("SimonBarnett/bobiverse")
    ok4, _ = lock.try_acquire("SimonBarnett/other", "b4")
    assert ok4


def test_fr4006_single_flight_allows_parallel_when_configured(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "locks.json", max_parallel=2)
    assert lock.try_acquire("a/b", "1")[0]
    assert lock.try_acquire("c/d", "2")[0]
    assert not lock.try_acquire("e/f", "3")[0]


def test_fr4006_decide_denied_for_worker():
    who = cc.Principal("none", "seat-1", "")
    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 0.1.32",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
    )
    assert dec and dec.ok is False and dec.reason == "denied"


def test_fr4006_decide_dry_run_and_no_recipe(tmp_path: Path):
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "l.json")

    def loader(repo: str):
        if "norecipe" in repo:
            raise bb.RecipeError(f"build: {repo} has no .bobiverse/build.yml; nothing started")
        return bb.load_recipe(ROOT)

    dec = bb.decide_build(
        who=who,
        body="!build dry-run SimonBarnett/bobiverse 0.1.32 HEAD",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader,
        lock=lock,
    )
    assert dec and dec.dry_run
    assert any("dry-run" in ln for ln in dec.pm_lines)
    assert lock.running_id("SimonBarnett/bobiverse") is None  # dry-run does not lock

    dec2 = bb.decide_build(
        who=who,
        body="!build SimonBarnett/norecipe 0.1.32",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader,
        lock=lock,
    )
    assert dec2 and any("no .bobiverse/build.yml" in ln for ln in dec2.pm_lines)


def test_fr4006_decide_run_acquires_lock(tmp_path: Path):
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json")
    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 0.1.32 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-test",
    )
    assert dec and dec.ok and "b-test" in " ".join(dec.pm_lines)
    assert lock.running_id("SimonBarnett/bobiverse") == "b-test"
    # second refused
    dec2 = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 0.1.32 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-2",
    )
    assert dec2 and any("refused" in ln for ln in dec2.pm_lines)


def test_fr4006_blocker_body_has_dedupe():
    f = bb.classify_failure("airc/tests/test_x.py::t", ref_failed=True, baseline_failed=False)
    body = bb.blocker_issue_body(repo="SimonBarnett/bobiverse", version="0.1.32", ref="abc", failure=f)
    assert "release-blocker" not in body  # labels separate
    assert "dedupe:" in body
    assert bb.FEATURE_REQUEST_LABEL == "feature-request"
    assert bb.RELEASE_BLOCKER_LABEL == "release-blocker"
