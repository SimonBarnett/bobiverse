"""FR #6491: chair releases home build-locks.json on terminal BUILD result (by id)
and on stale TTL at the next !build; cancel/status unchanged.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import bobiverse_build as bb
import chair_commands as cc
from repo_layout import ROOT


def test_fr6491_parse_build_result_ok_fail_with_id():
    ok = bb.parse_build_result(
        "BUILD ok SimonBarnett/bobiverse version=2.0.0 ref=main "
        "tag=v2.0.0 prerelease never_latest=True id=b-100"
    )
    assert ok is not None
    assert ok["kind"] == "ok"
    assert ok["repo"] == "SimonBarnett/bobiverse"
    assert ok["id"] == "b-100"

    fail = bb.parse_build_result(
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=main "
        "blockers=1 pack=False release=False id=b-101"
    )
    assert fail is not None
    assert fail["kind"] == "fail"
    assert fail["id"] == "b-101"

    refuse = bb.parse_build_result(
        "BUILD fail SimonBarnett/bobiverse version=2.0.0: wrong machine id=b-102"
    )
    assert refuse is not None
    assert refuse["kind"] == "fail"
    assert refuse["id"] == "b-102"

    assert bb.parse_build_result("BUILD v1 repos=a/b version=1.0.0 ref=HEAD") is None
    assert bb.parse_build_result("build: queued a/b") is None
    bare = bb.parse_build_result("BUILD ok SimonBarnett/bobiverse version=1.0.0 ref=HEAD")
    assert bare is not None and bare["id"] == ""


def test_fr6491_release_if_id_matches_only(tmp_path: Path):
    lock = bb.BuildLock(tmp_path / "build-locks.json", max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-X")[0]
    assert lock.release_if_id("SimonBarnett/bobiverse", "b-OTHER") is False
    assert lock.running_id("SimonBarnett/bobiverse") == "b-X"
    assert lock.release_if_id("SimonBarnett/bobiverse", "b-X") is True
    assert lock.running_id("SimonBarnett/bobiverse") is None


def test_fr6491_terminal_result_releases_chair_lock_by_id(tmp_path: Path):
    """Acceptance: terminal BUILD for id X releases chair lock; other id does not."""
    lock_path = tmp_path / "home" / "build-locks.json"
    lock = bb.BuildLock(lock_path, max_parallel=1)
    lock.try_acquire("SimonBarnett/bobiverse", "b-1794393946")

    other = bb.parse_build_result(
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=main blockers=0 "
        "pack=False release=False id=b-other"
    )
    assert other and other["id"] == "b-other"
    assert (
        bb.apply_build_result_to_chair_lock(lock, other) is False
    )
    assert lock.running_id("SimonBarnett/bobiverse") == "b-1794393946"

    terminal = bb.parse_build_result(
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=main blockers=0 "
        "pack=False release=False id=b-1794393946"
    )
    assert terminal and terminal["id"] == "b-1794393946"
    assert bb.apply_build_result_to_chair_lock(lock, terminal) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None


def test_fr6491_stale_lock_released_on_next_build_fresh_refuses(tmp_path: Path):
    """Acceptance: stale lock released on next !build; fresh lock still refuses."""
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    lock.try_acquire("SimonBarnett/bobiverse", "b-old")
    # Force started far in the past.
    data = lock._read()
    data["builds"]["simonbarnett/bobiverse"]["started"] = time.time() - 99_000
    lock._write(data)

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-new",
        stale_max_age_s=3600.0,
    )
    assert dec and dec.ok
    assert lock.running_id("SimonBarnett/bobiverse") == "b-new"
    assert any("stale" in ln.lower() for ln in dec.pm_lines)
    assert "id=b-new" in (dec.route or "")

    # Fresh lock (just acquired) must still refuse.
    dec2 = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.1 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-2",
        stale_max_age_s=3600.0,
    )
    assert dec2 and any("refused" in ln and "b-new" in ln for ln in dec2.pm_lines)
    assert lock.running_id("SimonBarnett/bobiverse") == "b-new"


def test_fr6491_cancel_and_status_unchanged(tmp_path: Path):
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "l.json")
    lock.try_acquire("SimonBarnett/bobiverse", "b-1")

    st = bb.decide_build(
        who=who,
        body="!build status SimonBarnett/bobiverse",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
    )
    assert st and st.status_only and "b-1" in " ".join(st.pm_lines)

    cancel = bb.decide_build(
        who=who,
        body="!build cancel SimonBarnett/bobiverse",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
    )
    assert cancel and cancel.cancel
    assert lock.running_id("SimonBarnett/bobiverse") is None


def test_fr6491_route_and_announce_carry_id(tmp_path: Path):
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json")
    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-route",
    )
    assert dec and dec.ok
    assert dec.route == (
        "BUILD v1 repos=SimonBarnett/bobiverse version=2.0.0 ref=main id=b-route"
    )
    job = bb.enqueue_build_job(
        bb.parse_build_v1_route(dec.route),
        queue_dir=tmp_path / "q",
        local_machine="flamingo",
        recipe_machine="flamingo",
    )
    payload = __import__("json").loads(job.read_text(encoding="utf-8"))
    assert payload.get("id") == "b-route"

    recipe = bb.load_recipe(ROOT)
    runner = bb.BuildRunner(
        repo_root=ROOT,
        repo="SimonBarnett/bobiverse",
        version="2.0.0",
        ref="main",
        recipe=recipe,
        filer=bb.FakeGitHubFiler(),
        work_dir=tmp_path / "w",
        log_dir=tmp_path / "logs",
        local_machine="other-box",
        build_id="b-route",
    )
    report = runner.run()
    assert any(
        ln.startswith("BUILD fail") and "id=b-route" in ln for ln in report.announce_lines
    )


def test_fr6491_chair_handler_releases_on_fleet_result(tmp_path: Path, monkeypatch):
    """Chair hears BUILD fail/ok on fleet channel and frees home lock by id."""
    import irc_agent as ia

    home = tmp_path / "jeeves-home"
    home.mkdir()
    lock = bb.BuildLock(home / "build-locks.json")
    lock.try_acquire("SimonBarnett/bobiverse", "b-live")

    args = SimpleNamespace(chair=True, home=str(home), nick="Jeeves")
    agent = ia.Client.__new__(ia.Client)
    agent.args = args
    agent.home = str(home)
    agent.original_nick = "Jeeves"
    agent.live_nick = "Jeeves"
    released = []

    def _info(msg: str) -> None:
        released.append(msg)

    monkeypatch.setattr(ia, "info", _info)
    body = (
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=main "
        "blockers=0 pack=False release=False id=b-live"
    )
    assert agent._maybe_release_chair_build_lock_on_result("Bob-flamingo", body) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None
    assert any("released" in m.lower() for m in released)

    lock.try_acquire("SimonBarnett/bobiverse", "b-live2")
    wrong = (
        "BUILD ok SimonBarnett/bobiverse version=2.0.0 ref=main "
        "tag=v2.0.0 prerelease never_latest=True id=b-wrong"
    )
    assert agent._maybe_release_chair_build_lock_on_result("Bob-flamingo", wrong) is True
    assert lock.running_id("SimonBarnett/bobiverse") == "b-live2"
