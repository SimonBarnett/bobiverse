"""FR #7183: one machine Grok sign-in; seats never copy credentials."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

import bob_worker as bw
import skill_dag_bound as bound


def _auth_blob(refresh: str) -> str:
    # Placeholders only (FR #3304); never a contiguous live JWT.
    return json.dumps(
        {
            "https://auth.x.ai::test": {
                "key": "FAKE_SESSION_KEY_FOR_TESTS_ONLY",
                "refresh_token": refresh,
            }
        }
    )


def test_prepare_seat_grok_home_does_not_copy_auth(tmp_path):
    user = tmp_path / "user-grok"
    user.mkdir()
    (user / "auth.json").write_text(_auth_blob("FAKE_REFRESH_A"), encoding="utf-8")
    (user / "config.toml").write_text("[skills]\npaths = [\"X\"]\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    trust = tmp_path / "bound"
    trust.mkdir()
    home = bound.prepare_seat_grok_home(run_dir, trust_paths=[trust], user_grok_home=user)
    assert home == run_dir / bound.GROK_HOME_NAME
    assert not (home / "auth.json").exists()
    assert (user / "auth.json").is_file()
    seat_cfg = (home / "config.toml").read_text(encoding="utf-8")
    assert "paths = []" in seat_cfg


def test_agent_child_sets_grok_auth_path_to_machine_store(tmp_path, monkeypatch):
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / ".grok" / "skills" / "noise").mkdir(parents=True)
    (worker / ".grok" / "skills" / "noise" / "SKILL.md").write_text(
        "---\nname: noise\ndescription: noise\n---\n", encoding="utf-8"
    )
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "common" / "scripts").mkdir(parents=True)
    (tmp_path / "common" / "scripts" / "skill_dag_mcp.py").write_text("#\n", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    user = tmp_path / "fake-user-grok"
    user.mkdir()
    auth = user / "auth.json"
    auth.write_text(_auth_blob("FAKE_REFRESH_A"), encoding="utf-8")
    monkeypatch.setenv("GROK_HOME", str(user))
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="agent",
        cwd=str(worker),
        run_dir=run_dir,
        machine="flamingo",
        nick="flamingo-1",
        agent_exe=r"C:\fake\agent.exe",
    )
    env = child["env"]
    assert env.get("GROK_HOME") == str(run_dir / bound.GROK_HOME_NAME)
    assert env.get("GROK_AUTH_PATH") == str(auth)
    assert not (run_dir / bound.GROK_HOME_NAME / "auth.json").exists()


@pytest.mark.parametrize("as_system", [False, True])
def test_machine_auth_path_system_and_tray_user(tmp_path, monkeypatch, as_system):
    profile = tmp_path / ("systemprofile" if as_system else "simon")
    grok = profile / ".grok"
    grok.mkdir(parents=True)
    auth = grok / "auth.json"
    auth.write_text(_auth_blob("FAKE_REFRESH_A"), encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("HOME", str(profile))
    monkeypatch.setenv("USERNAME", "SYSTEM" if as_system else "simon")
    monkeypatch.delenv("BOB_GROK_AUTH_PATH", raising=False)
    monkeypatch.delenv("GROK_HOME", raising=False)
    monkeypatch.delenv("GROK_AUTH_PATH", raising=False)
    got = bound.machine_grok_auth_path()
    assert got == auth
    assert bound.grok_session_usable(auth_path=got) is True


def test_concurrent_refresh_one_valid_token(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text(_auth_blob("FAKE_REFRESH_OLD"), encoding="utf-8")
    results: list[str] = []

    def _seat(token: str) -> None:
        bound.commit_refreshed_auth(auth, _auth_blob(token))
        results.append(token)

    t1 = threading.Thread(target=_seat, args=("FAKE_REFRESH_ONE",))
    t2 = threading.Thread(target=_seat, args=("FAKE_REFRESH_TWO",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    body = auth.read_text(encoding="utf-8")
    obj = json.loads(body)
    token = obj["https://auth.x.ai::test"]["refresh_token"]
    assert token in ("FAKE_REFRESH_ONE", "FAKE_REFRESH_TWO")
    assert results == ["FAKE_REFRESH_ONE", "FAKE_REFRESH_TWO"] or set(results) == {
        "FAKE_REFRESH_ONE",
        "FAKE_REFRESH_TWO",
    }
    assert "FAKE_REFRESH_OLD" not in body
    assert bound.grok_session_usable(auth_path=auth) is True


def test_needs_signin_line_never_ready():
    line = bw.worker_needs_signin_line("grok", build="abc123def456")
    assert line.startswith("worker needs sign-in ")
    assert "ready" not in line
    assert "kind=grok" in line
    assert "abc123def456" in line
    assert "FAKE_" not in line
    assert "refresh" not in line.lower()


def test_post_digest_needs_sign_in_state(monkeypatch):
    seen = {}

    def _post(url, payload, log=None):  # noqa: ARG001
        seen.update(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _post)
    monkeypatch.setenv("BOB_REPORT_URL", "https://example.invalid/report")
    ok = bw.post_digest_seat_kind(
        machine="flamingo",
        pid=1,
        nick="flamingo-1",
        kind="grok",
        worker_build="abc123def456",
        state="needs_sign_in",
    )
    assert ok
    assert seen.get("state") == "needs_sign_in"
    assert seen.get("state") != "idle"
    assert "refresh" not in json.dumps(seen).lower()


def test_bored_busy_when_needs_signin():
    sent = []
    b = bw.BoredEmitter(lambda: sent.append("bored") or True, lambda m: None, idle_s=0, repeat_s=99)
    b.set_ready(True)
    b.note_needs_signin()
    assert b._busy(b.clock()) is True
    assert sent == []


def test_grok_session_usable_false_when_missing(tmp_path):
    assert bound.grok_session_usable(auth_path=tmp_path / "nope.json") is False
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert bound.grok_session_usable(auth_path=empty) is False
