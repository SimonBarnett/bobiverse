"""#4183: BUILD suites never touch the live chair home or port."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobiverse_build as bb  # noqa: E402


def test_isolated_env_redirects_homes_and_urls(tmp_path):
    env = bb.isolated_suite_env(tmp_path, "jeeves-ref")
    for k in ("USERPROFILE", "HOME", "BOB_HOME", "BOB_DIGEST_HOME", "ProgramData", "BOB_CONFIG_DIR"):
        assert str(tmp_path) in env[k]
    assert env["BOB_REPORT_PORT"] != "7700"
    assert "irc.ntsa.uk" not in env["BOB_DIGEST_URL"]
    assert env["GH_TOKEN"] == ""


def test_guard_passes_isolated_env_and_detects_live_write(tmp_path):
    live = tmp_path / "live" / ".bobiverse"
    live.mkdir(parents=True)
    rows = ",".join('{"repo":"o/r","task":"FR","id":"#%d"}' % i for i in range(10))
    (live / "queue.json").write_text('{"v":1,"unaccepted":[%s]}' % rows, encoding="utf-8")
    seen = {}

    def ok(cmd, cwd=None, env=None, timeout=None, *, name="", ref_or_baseline=""):
        seen.update(env)
        return "ok"

    run = bb.guarded_run_command(tmp_path / "work", [live], inner=ok)
    assert run("x", name="jeeves", ref_or_baseline="HEAD") == "ok"
    assert str(tmp_path / "work") in seen["BOB_DIGEST_HOME"]

    def clobber(cmd, cwd=None, env=None, timeout=None, *, name="", ref_or_baseline=""):
        (live / "queue.json").write_text('{"v":1,"unaccepted":[]}', encoding="utf-8")
        return "ok"

    run2 = bb.guarded_run_command(tmp_path / "work", [live], inner=clobber)
    with pytest.raises(bb.LiveStateTouched):
        run2("x", name="jeeves", ref_or_baseline="HEAD")


def test_guarded_real_subprocess_sees_isolated_profile(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    run = bb.guarded_run_command(tmp_path / "work", [live])
    res = run([sys.executable, "-c", "import os;print(os.environ['BOB_DIGEST_HOME'])"],
              cwd=str(tmp_path), timeout=60, name="probe", ref_or_baseline="HEAD")
    assert str(tmp_path / "work") in res.stdout


def test_routine_rewrite_is_not_damage(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    (live / "queue.json").write_text('{"v":1,"unaccepted":[{"repo":"o/r","task":"FR","id":"#1"}]}', encoding="utf-8")
    (live / "registered-machines.json").write_text("{}", encoding="utf-8")

    def touch(cmd, cwd=None, env=None, timeout=None, *, name="", ref_or_baseline=""):
        (live / "registered-machines.json").write_text('{"refreshed_ts": 2}', encoding="utf-8")
        (live / "queue.json").write_text('{"v":1,"unaccepted":[{"repo":"o/r","task":"FR","id":"#1","seq":2}]}', encoding="utf-8")
        return "ok"

    assert bb.guarded_run_command(tmp_path / "w", [live], inner=touch)("x", name="j", ref_or_baseline="H") == "ok"


def test_fr4315_suite_env_cannot_clobber_digest_home(tmp_path):
    """Caller/suite.env pointing at the live chair must lose to isolation (FR #4315)."""
    live = tmp_path / "live" / ".bobiverse"
    live.mkdir(parents=True)
    seen = {}

    def capture(cmd, cwd=None, env=None, timeout=None, *, name="", ref_or_baseline=""):
        seen.update(env or {})
        return "ok"

    run = bb.guarded_run_command(tmp_path / "work", [live], inner=capture)
    run(
        "x",
        env={"BOB_DIGEST_HOME": str(live), "USERPROFILE": str(tmp_path / "live")},
        name="common",
        ref_or_baseline="HEAD",
    )
    assert str(tmp_path / "work") in seen["BOB_DIGEST_HOME"]
    assert seen["BOB_DIGEST_HOME"] != str(live)
    assert seen.get("BOBIVERSE_BUILD_SUITE") == "1"


def _focus_doc(repos=None, items=None):
    import json

    return json.dumps(
        {"v": 1, "repos": repos or {}, "items": items or {}, "item_seq": 0, "strict": False}
    )


def test_fr4408_one_focus_prune_is_not_damage(tmp_path):
    """Concurrent chair prune of one closed focus item must not abort !build (#4408)."""
    live = tmp_path / "live" / ".bobiverse"
    live.mkdir(parents=True)
    (live / "focus.json").write_text(
        _focus_doc(
            items={
                "o/r#1": {"rank": 1, "repo": "o/r", "id": "#1"},
                "o/r#2": {"rank": 2, "repo": "o/r", "id": "#2"},
            }
        ),
        encoding="utf-8",
    )

    def prune_one(cmd, cwd=None, env=None, timeout=None, *, name="", ref_or_baseline=""):
        (live / "focus.json").write_text(
            _focus_doc(items={"o/r#2": {"rank": 2, "repo": "o/r", "id": "#2"}}),
            encoding="utf-8",
        )
        return "ok"

    run = bb.guarded_run_command(tmp_path / "work", [live], inner=prune_one)
    assert run("x", name="bob", ref_or_baseline="HEAD") == "ok"


def test_fr4408_mass_focus_loss_is_damage(tmp_path):
    """Wiping more than max_lost focus keys still fails closed (#4183 / #4408)."""
    live = tmp_path / "live" / ".bobiverse"
    live.mkdir(parents=True)
    items = {f"o/r#{i}": {"rank": i, "repo": "o/r", "id": f"#{i}"} for i in range(8)}
    (live / "focus.json").write_text(_focus_doc(items=items), encoding="utf-8")

    def wipe(cmd, cwd=None, env=None, timeout=None, *, name="", ref_or_baseline=""):
        (live / "focus.json").write_text(_focus_doc(), encoding="utf-8")
        return "ok"

    run = bb.guarded_run_command(tmp_path / "work", [live], inner=wipe)
    with pytest.raises(bb.LiveStateTouched, match="focus.json lost"):
        run("x", name="bob", ref_or_baseline="HEAD")


def test_fr4408_live_state_damage_focus_threshold():
    before = {"/x/focus.json": {"a", "b", "c", "d", "e", "f", "g"}}
    after_ok = {"/x/focus.json": {"a", "b", "c", "d", "e", "f"}}  # lost 1
    after_bad = {"/x/focus.json": {"a"}}  # lost 6
    assert bb.live_state_damage(before, after_ok) == []
    assert bb.live_state_damage(before, after_bad) == ["/x/focus.json lost 6"]
