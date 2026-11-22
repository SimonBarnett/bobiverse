"""FR #6715: chair !build honours reserved subcommands before starting a run.

``!build cancel`` (bare or with catalog n) must never enqueue a runner; unknown
subcommands/arguments are refused with usage, and a plain catalog build still queues.
"""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import builds_catalog as bc
import chair_commands as cc
from repo_layout import ROOT

OWNER = cc.Principal("owner", "simon", "simon")


def _cat():
    return [
        bc.BuildCatalogEntry(
            name="Bobiverse",
            yml="SimonBarnett/bobiverse:.bobiverse/build.yml",
            output=r"D:\Temp\bobiverse-build",
            install="fleet",
        )
    ]


def _decide(body: str, lock: bb.BuildLock | None = None, *, loader=None, catalog=None):
    return bb.decide_build(
        who=OWNER,
        body=body,
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader or (lambda r: bb.load_recipe(ROOT)),
        lock=lock,
        new_build_id=lambda: "b-test",
        catalog_entries=_cat() if catalog is None else catalog,
    )


def test_fr6715_parse_build_reserved_verbs():
    assert bb.parse_build("!build cancel") == (True, "cancel", "")
    assert bb.parse_build("!build CANCEL") == (True, "cancel", "")
    assert bb.parse_build("!build cancel 1") == (True, "cancel", "1")
    assert bb.parse_build("!build status 1")[1] == "status"
    assert bb.parse_build("!build dry-run 1 2.0.0")[1] == "dry-run"
    assert bb.parse_build("!build preflight 1")[1] == "preflight"


def test_fr6715_bare_cancel_cancels_running_build_and_never_runs(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json")
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-live")[0]

    def _no_recipe(_repo: str):
        raise AssertionError("cancel must not load a recipe or start a runner")

    dec = _decide("!build cancel", lock, loader=_no_recipe)
    assert dec is not None and dec.ok and dec.cancel
    assert dec.route == ""
    assert any("cancelled" in ln and "b-live" in ln for ln in dec.pm_lines)
    assert lock.running() == []


def test_fr6715_bare_cancel_with_nothing_running(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json")
    dec = _decide("!build cancel", lock)
    assert dec is not None and not dec.ok
    assert dec.reason == "nothing_running"
    assert "no build running" in " ".join(dec.pm_lines).lower()
    assert dec.route == ""


def test_fr6715_cancel_repo_when_running_and_when_not(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json")
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-live")[0]

    dec = _decide("!build cancel 1", lock)
    assert dec is not None and dec.ok and dec.cancel
    assert lock.running_id("SimonBarnett/bobiverse") is None

    again = _decide("!build cancel 1", lock)
    assert again is not None and not again.ok
    assert "no build running" in " ".join(again.pm_lines).lower()


def test_fr6715_unknown_subcommand_or_argument_usage_no_run(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json")
    for body in (
        "!build frobnicate",
        "!build frobnicate 1.2.3",
        "!build cancelx SimonBarnett/bobiverse 1.2.3",
        "!build preflightx SimonBarnett/bobiverse 1.2.3",
    ):
        dec = _decide(body, lock)
        assert dec is not None and not dec.ok, body
        assert dec.reason == "usage", body
        assert dec.route == "", body
        # FR #8770: generic refusals return BUILD_USAGE_LINES (no longer contain "usage").
        assert any(
            "usage" in ln
            or "owner/repo form removed" in ln
            or ln in bb.BUILD_USAGE_LINES
            for ln in dec.pm_lines
        ), body
    assert lock.running() == []

    # Old owner/repo form is refused (FR #8490); bad version still refused on catalog form.
    old = _decide("!build SimonBarnett/bobiverse not-a-version", lock)
    assert old is not None and not old.ok and old.route == ""
    assert old.reason == "usage"
    assert any("owner/repo form removed" in ln for ln in old.pm_lines)

    bad = _decide("!build 1 not-a-version", lock)
    assert bad is not None and not bad.ok and bad.route == ""
    assert bad.reason == "bad_version"
    assert lock.running() == []


def test_fr6715_plain_build_still_queues(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json")

    empty = _decide("!build", lock, catalog=[])
    assert empty is not None and empty.ok
    assert empty.reason == "list"
    assert empty.route == ""
    assert any("catalog empty" in ln for ln in empty.pm_lines)

    dec = _decide("!build 1 2.0.0 main", lock)
    assert dec is not None and dec.ok
    assert dec.route.startswith("BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0")
    assert lock.running_id("SimonBarnett/bobiverse") == "b-test"
