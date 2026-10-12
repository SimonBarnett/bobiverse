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
