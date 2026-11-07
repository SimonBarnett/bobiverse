"""FR #6204: no unsolicited Copilot quota probe while dispatch is disabled."""
from __future__ import annotations

import json

import bobreport
import chair_health as ch
import copilot_dispatch as cd

NOW = 1_700_000_000.0
UNLIMITED = {
    "quota_snapshots": {
        "premium_interactions": {
            "entitlement": -1,
            "remaining": -1,
            "unlimited": True,
            "percent_remaining": 100,
        }
    }
}


def _iso(epoch: float) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def test_should_observe_false_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    assert cd.dispatch_enabled(tmp_path) is False
    assert cd.observation_opt_in(tmp_path) is False
    assert cd.should_observe_quota(tmp_path) is False


def test_observation_opt_in_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_COPILOT_OBSERVE", "yes")
    assert cd.observation_opt_in(tmp_path) is True
    assert cd.should_observe_quota(tmp_path) is True
    assert cd.dispatch_enabled(tmp_path) is False


def test_observation_opt_in_via_allowance_observe_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    (tmp_path / cd.ALLOWANCE_NAME).write_text(
        json.dumps({"enabled": False, "observe": True, "state": "ok"}) + "\n",
        encoding="utf-8",
    )
    assert cd.dispatch_enabled(tmp_path) is False
    assert cd.observation_opt_in(tmp_path) is True
    assert cd.should_observe_quota(tmp_path) is True


def test_observation_opt_in_via_observation_enabled_block(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    (tmp_path / cd.ALLOWANCE_NAME).write_text(
        json.dumps(
            {"enabled": False, "observation": {"enabled": True}, "state": "ok"}
        )
        + "\n",
        encoding="utf-8",
    )
    assert cd.dispatch_enabled(tmp_path) is False
    assert cd.observation_opt_in(tmp_path) is True


def test_env_off_overrides_allowance_observe(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_COPILOT_OBSERVE", "0")
    (tmp_path / cd.ALLOWANCE_NAME).write_text(
        json.dumps({"enabled": False, "observe": True}) + "\n",
        encoding="utf-8",
    )
    assert cd.observation_opt_in(tmp_path) is False


def test_dispatch_enabled_implies_should_observe(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    monkeypatch.delenv("BOB_FUEL_COPILOT", raising=False)
    cd.set_allowance(tmp_path, remaining=3)
    assert cd.dispatch_enabled(tmp_path) is True
    assert cd.should_observe_quota(tmp_path) is True


def test_chair_tick_dispatch_enabled_still_observes(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    monkeypatch.delenv("BOB_FUEL_COPILOT", raising=False)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    cd.set_allowance(tmp_path, remaining=2)
    calls = {"n": 0}

    class Clock:
        def __call__(self):
            return NOW

    def github_json(method, url, body=None):
        calls["n"] += 1
        if "copilot_internal/user" in url:
            return UNLIMITED, 200
        return {"status": 200}, 200

    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=lambda *_a, **_k: None,
        http=lambda *a, **k: 200,
        fetch_json=lambda url: [],
        token_loader=lambda: ("FAKE_token_for_tests_only", "file:x"),
        clock=Clock(),
        sleep=lambda s: None,
        spawn=False,
        owners={"SimonBarnett"},
    )
    j._github_json = github_json  # type: ignore[method-assign]
    assert cd.dispatch_enabled(tmp_path) is True
    j._copilot_tick()
    assert cd.observation_path(tmp_path).is_file()
    assert cd.load_observation(tmp_path)["fetched_at"] == _iso(NOW)
    assert calls["n"] >= 1
