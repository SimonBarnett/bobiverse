"""FR #6715: chair !build honours reserved subcommands before starting a run.

``!build cancel`` (bare or with a repo) must never enqueue a runner; unknown
subcommands/arguments are refused with usage, and a plain build still queues.
"""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import chair_commands as cc
from repo_layout import ROOT

OWNER = cc.Principal("owner", "simon", "simon")


def _decide(body: str, lock: bb.BuildLock | None = None, *, loader=None):
    return bb.decide_build(
        who=OWNER,
        body=body,
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader or (lambda r: bb.load_recipe(ROOT)),
        lock=lock,
        new_build_id=lambda: "b-test",
    )


def test_fr6715_parse_build_reserved_verbs():
    assert bb.parse_build("!build cancel") == (True, "cancel", "")
    assert bb.parse_build("!build CANCEL") == (True, "cancel", "")
    assert bb.parse_build("!build cancel SimonBarnett/bobiverse") == (
        True,
        "cancel",
        "SimonBarnett/bobiverse",
    )
    assert bb.parse_build("!build status SimonBarnett/bobiverse")[1] == "status"
    assert bb.parse_build("!build dry-run SimonBarnett/bobiverse 2.0.0")[1] == "dry-run"
    assert bb.parse_build("!build preflight SimonBarnett/bobiverse")[1] == "preflight"


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

    dec = _decide("!build cancel SimonBarnett/bobiverse", lock)
    assert dec is not None and dec.ok and dec.cancel
    assert lock.running_id("SimonBarnett/bobiverse") is None

    again = _decide("!build cancel SimonBarnett/bobiverse", lock)
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
        assert any("usage" in ln for ln in dec.pm_lines), body
    assert lock.running() == []

    # A bad version keeps its FR #4186 refusal (still no runner).
    bad = _decide("!build SimonBarnett/bobiverse not-a-version", lock)
    assert bad is not None and not bad.ok and bad.route == ""
    assert bad.reason == "bad_version"
    assert lock.running() == []


def test_fr6715_plain_build_still_queues(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json")

    empty = _decide("!build", lock)
    assert empty is not None and not empty.ok
    assert empty.reason == "usage"
    assert empty.route == ""

    dec = _decide("!build SimonBarnett/bobiverse 2.0.0 main", lock)
    assert dec is not None and dec.ok
    assert dec.route.startswith("BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0")
    assert lock.running_id("SimonBarnett/bobiverse") == "b-test"
