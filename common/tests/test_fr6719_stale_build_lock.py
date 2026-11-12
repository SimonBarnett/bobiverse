"""FR #6719: clear stale chair build lock after failed/dead runner; live still refuses."""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import bobiverse_build as bb
import chair_commands as cc
from repo_layout import ROOT


def test_fr6719_failed_build_clears_lock_then_rebuild(tmp_path: Path):
    """Acceptance: BUILD fail clears the running record; following !build is accepted."""
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-fail")[0]

    fail = bb.parse_build_result(
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=main "
        "blockers=1 pack=False release=False id=b-fail"
    )
    assert fail and fail["id"] == "b-fail"
    assert bb.apply_build_result_to_chair_lock(lock, fail) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-next",
    )
    assert dec and dec.ok
    assert lock.running_id("SimonBarnett/bobiverse") == "b-next"
    assert any("id=b-next" in ln for ln in dec.pm_lines)


def test_fr6719_dead_runner_no_heartbeat_releases_on_next_build(tmp_path: Path):
    """Acceptance: lock with no recent heartbeat is stale; next !build accepted."""
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    lock.try_acquire("SimonBarnett/bobiverse", "b-1794440818")
    # Simulate a runner that died hours ago without a terminal announce.
    data = lock._read()
    past = time.time() - 7200
    data["builds"]["simonbarnett/bobiverse"]["started"] = past
    data["builds"]["simonbarnett/bobiverse"]["last_seen"] = past
    lock._write(data)

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-retry",
        dead_max_age_s=1800.0,  # 30 min bound
        stale_max_age_s=99_000.0,  # recipe TTL would NOT have fired yet
    )
    assert dec and dec.ok
    assert lock.running_id("SimonBarnett/bobiverse") == "b-retry"
    blob = " ".join(dec.pm_lines).lower()
    assert "stale" in blob and "no-heartbeat" in blob
    assert "b-1794440818" in " ".join(dec.pm_lines)


def test_fr6719_live_build_still_refuses(tmp_path: Path):
    """Acceptance: genuinely live lock refuses; message says live."""
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    lock.try_acquire("SimonBarnett/bobiverse", "b-live")
    # Fresh heartbeat keeps the lock live under the dead-runner bound.
    assert lock.touch("SimonBarnett/bobiverse", "b-live") is True

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.1 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-2",
        dead_max_age_s=1800.0,
        stale_max_age_s=99_000.0,
    )
    assert dec is not None
    assert any(
        "refused" in ln and "b-live" in ln and "(live)" in ln for ln in dec.pm_lines
    )
    assert lock.running_id("SimonBarnett/bobiverse") == "b-live"


def test_fr6719_progress_line_refreshes_last_seen(tmp_path: Path):
    """Chair progress parse + touch keep a quiet-but-alive runner under the bound."""
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    lock.try_acquire("SimonBarnett/bobiverse", "b-hb")
    data = lock._read()
    data["builds"]["simonbarnett/bobiverse"]["last_seen"] = time.time() - 1000
    lock._write(data)
    assert lock.last_seen_age_s("SimonBarnett/bobiverse") >= 999

    prog = bb.parse_build_progress(
        "BUILD progress SimonBarnett/bobiverse version=2.0.0 "
        "heartbeat step=suite step_s=10 run_s=600 id=b-hb"
    )
    assert prog and prog["id"] == "b-hb"
    assert bb.apply_build_progress_to_chair_lock(lock, prog) is True
    assert lock.last_seen_age_s("SimonBarnett/bobiverse") < 5


def test_fr6719_chair_handler_touches_on_progress(tmp_path: Path, monkeypatch):
    import irc_agent as ia

    home = tmp_path / "jeeves-home"
    home.mkdir()
    lock = bb.BuildLock(home / "build-locks.json")
    lock.try_acquire("SimonBarnett/bobiverse", "b-hb")
    data = lock._read()
    data["builds"]["simonbarnett/bobiverse"]["last_seen"] = time.time() - 5000
    lock._write(data)

    args = SimpleNamespace(chair=True, home=str(home), nick="Jeeves")
    agent = ia.Client.__new__(ia.Client)
    agent.args = args
    agent.home = str(home)
    agent.original_nick = "Jeeves"
    agent.live_nick = "Jeeves"
    logs: list[str] = []
    monkeypatch.setattr(ia, "info", logs.append)

    body = (
        "BUILD progress SimonBarnett/bobiverse version=2.0.0 "
        "step start suite id=b-hb"
    )
    assert agent._maybe_touch_chair_build_lock_on_progress("Bob-flamingo", body) is True
    assert lock.last_seen_age_s("SimonBarnett/bobiverse") < 5
    assert any("6719" in m and "heartbeat" in m.lower() for m in logs)
