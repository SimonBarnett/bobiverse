"""FR #6484: packaged Jeeves !build falls back to GitHub bobiverse recipe."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import chair_commands as cc
from repo_layout import ROOT

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobiverse_build as bb  # noqa: E402


def _cp(rc=0, out="", err=""):
    return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


_REMOTE_YML = (
    "machine: flamingo\n"
    "suites:\n"
    "  - name: common\n"
    "    cmd: python -m pytest -q common/tests\n"
    "release:\n"
    "  target: github-prerelease\n"
)


def test_fr6484_fetch_remote_recipe_passes_ref():
    calls = []

    def gh(args, **k):
        calls.append(args)
        return _cp(0, _REMOTE_YML)

    r = bb.fetch_remote_recipe("SimonBarnett/bobiverse", ref="main", gh_runner=gh)
    assert r is not None
    assert r.machine == "flamingo"
    joined = " ".join(calls[0])
    assert "repos/simonbarnett/bobiverse/contents/.bobiverse/build.yml" in joined.lower()
    assert "ref=main" in joined


def test_fr6484_local_recipe_preferred(tmp_path: Path):
    remote_calls = []

    def gh(args, **k):
        remote_calls.append(args)
        return _cp(0, _REMOTE_YML)

    r = bb.load_bobiverse_recipe_local_or_remote(
        [ROOT],
        "SimonBarnett/bobiverse",
        ref="main",
        gh_runner=gh,
    )
    assert r.machine == "flamingo"
    assert remote_calls == []


def test_fr6484_remote_fallback_when_local_missing(tmp_path: Path):
    empty = tmp_path / "packaged-install"
    empty.mkdir()
    calls = []

    def gh(args, **k):
        calls.append(args)
        return _cp(0, _REMOTE_YML)

    r = bb.load_bobiverse_recipe_local_or_remote(
        [empty, empty.parent],
        "SimonBarnett/bobiverse",
        ref="HEAD",
        gh_runner=gh,
    )
    assert r.machine == "flamingo"
    assert calls, "expected remote fetch"
    assert "ref=main" in " ".join(calls[0])  # HEAD maps to main for contents API


def test_fr6484_remote_fail_refuses_nothing_started(tmp_path: Path):
    empty = tmp_path / "packaged"
    empty.mkdir()

    def gh(args, **k):
        return _cp(1, "", "HTTP 404: Not Found")

    try:
        bb.load_bobiverse_recipe_local_or_remote(
            [empty],
            "SimonBarnett/bobiverse",
            ref="main",
            gh_runner=gh,
        )
        assert False, "expected RecipeError"
    except bb.RecipeError as exc:
        assert "no .bobiverse/build.yml" in str(exc)
        assert "nothing started" in str(exc)


def test_fr6484_decide_build_uses_remote_loader(tmp_path: Path):
    """Acceptance: !build with no local yml loads remote and announces recipe machine."""
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "locks.json")
    empty = tmp_path / "install"
    empty.mkdir()

    def gh(args, **k):
        return _cp(0, _REMOTE_YML)

    def loader(repo: str):
        return bb.load_bobiverse_recipe_local_or_remote(
            [empty],
            repo,
            ref="main",
            gh_runner=gh,
        )

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=loader,
        lock=lock,
        new_build_id=lambda: "b-6484",
    )
    assert dec is not None
    assert dec.ok is True
    joined = "\n".join(dec.pm_lines)
    assert "machine=flamingo" in joined
    assert "nothing started" not in joined


def test_fr6484_irc_agent_build_loader_pins_fallback():
    src = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "irc_agent.py"
    ).read_text(encoding="utf-8")
    assert "load_bobiverse_recipe_local_or_remote" in src
    assert "FR #6484" in src
