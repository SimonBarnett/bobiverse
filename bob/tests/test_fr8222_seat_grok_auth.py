"""FR #8222: provision seat auth.json; missing login is no-seat-auth."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bob_worker as bw
import skill_dag_bound as bound


def _blob(expires_at):
    body = {
        "https://auth.x.ai::test": {
            "key": "FAKE_SESSION_KEY_FOR_TESTS_ONLY",
            "refresh_token": "FAKE_REFRESH_A",
        }
    }
    if expires_at is not None:
        body["https://auth.x.ai::test"]["expires_at"] = expires_at
    return json.dumps(body)


def test_fresh_seat_gets_login_and_no_prompt_path(tmp_path):
    user = tmp_path / "user-grok"
    user.mkdir()
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (user / "auth.json").write_text(_blob(future), encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    home = bound.prepare_seat_grok_home(run, user_grok_home=user)
    seat = home / "auth.json"
    assert seat.is_file()
    summary = bound.summarize_grok_auth(seat)
    assert summary["present"] is True
    assert summary["usable"] is True
    assert summary["expired"] is False
    assert "key" not in json.dumps({k: summary[k] for k in ("present", "usable", "expired", "expires_at")})
    # Same bytes as the machine file (link or copy). Launch does not need a sign-in prompt.
    assert seat.read_text(encoding="utf-8") == (user / "auth.json").read_text(encoding="utf-8")


def test_missing_machine_login_is_no_seat_auth_not_expired():
    fuel = bw.Fuel(0, 0, 0, "available")
    d = bw.apply_xai_signin_gate(
        bw.Decision("grok", "would-start"),
        fuel,
        None,
        r"C:\g\agent.exe",
        None,
        signin_ok=False,
        signin_state="absent",
        machine="flamingo",
    )
    assert d.kind == "no-seat-auth"
    assert "no-seat-auth" in d.reason
    assert "no Grok login on flamingo" in d.reason
    assert "expired" not in d.reason
    assert "xai-auth-expired" not in d.reason


def test_signin_prompt_distinguishes_missing_seat_from_expired_machine(tmp_path):
    seat = tmp_path / "grok-home"
    seat.mkdir()
    machine = tmp_path / "auth.json"
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    machine.write_text(_blob(past), encoding="utf-8")
    assert (
        bw.classify_grok_signin_prompt_cause(seat_home=seat, machine_auth=machine)
        == "xai-auth-expired"
    )
    empty = tmp_path / "none" / "auth.json"
    assert (
        bw.classify_grok_signin_prompt_cause(seat_home=seat, machine_auth=empty)
        == "no-seat-auth"
    )
    d = bw.decision_after_grok_signin_prompt(
        bw.Fuel(0, 0, 0, "available"),
        None,
        None,
        seat_home=seat,
        machine_auth=empty,
        machine="flamingo",
    )
    assert d.kind == "no-seat-auth"
    assert "expired" not in d.reason


def test_expired_machine_is_not_provisioned(tmp_path):
    user = tmp_path / "user-grok"
    user.mkdir()
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (user / "auth.json").write_text(_blob(past), encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    home = bound.prepare_seat_grok_home(run, user_grok_home=user)
    assert not (home / "auth.json").exists()
    summary = bound.summarize_grok_auth(user / "auth.json")
    assert summary["expired"] is True
    assert summary["usable"] is False
    assert "FAKE_" not in json.dumps(summary)
