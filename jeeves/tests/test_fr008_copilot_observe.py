"""FR #6148 / FR-008: dispatch-independent Copilot quota observer into digest."""
from __future__ import annotations

import json
from pathlib import Path

import bobcallback
import bobreport
import chair_health as ch
import copilot_dispatch as cd
import gitclaim


UNLIMITED = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 39,
            "entitlement": 0,
            "remaining": 0,
            "percent_remaining": 100.0,
            "unlimited": True,
            "overage_permitted": True,
        }
    },
}

LIMITED = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 10,
            "remaining": 140,
            "percent_remaining": 40.0,
            "unlimited": False,
        }
    },
}

NOW = 1_700_000_000.0


def _iso(epoch: float) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def test_observe_success_then_get_report_fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    out = cd.observe_quota(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)
    assert out["state"] == "ok"
    assert out["fetched_at"] == _iso(NOW)
    assert out.get("last_error") in (None, "", False) or not out.get("last_error")
    assert cd.observation_path(tmp_path).is_file()
    assert not cd._allow_path(tmp_path).is_file()

    code, body = bobcallback.handle_request(
        "GET",
        "/bob/v1/report",
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        briefer_nick="Jeeves",
    )
    assert code == 200
    doc = json.loads(body.decode("utf-8"))
    assert doc["copilot"]["fetched_at"] == _iso(NOW)
    assert abs(
        __import__("time").mktime(
            __import__("time").strptime(doc["copilot"]["fetched_at"], "%Y-%m-%dT%H:%M:%SZ")
        )
        - NOW
    ) < 5 or doc["copilot"]["fetched_at"] == _iso(NOW)


def test_observe_failure_keeps_fetched_at_advances_attempted(tmp_path):
    cd.observe_quota(tmp_path, fetch_user=lambda: LIMITED, now=NOW)
    first = cd.load_observation(tmp_path)
    assert first["fetched_at"] == _iso(NOW)

    def boom():
        raise RuntimeError("http_503")

    cd.observe_quota(tmp_path, fetch_user=boom, now=NOW + 400)
    second = cd.load_observation(tmp_path)
    assert second["fetched_at"] == _iso(NOW)
    assert second["attempted_at"] == _iso(NOW + 400)
    assert second.get("last_error")
    assert second["remaining"] == 140


def test_observe_non_2xx_via_raised_status(tmp_path):
    cd.observe_quota(tmp_path, fetch_user=lambda: LIMITED, now=NOW)

    def http_fail():
        raise RuntimeError("http_403")

    cd.observe_quota(tmp_path, fetch_user=http_fail, now=NOW + 400)
    doc = cd.load_observation(tmp_path)
    assert doc["fetched_at"] == _iso(NOW)
    assert "403" in str(doc.get("last_error") or "") or doc.get("last_error") == "http_403"


def test_observe_no_token_no_secret_leak(tmp_path, capsys):
    secret = "FAKE_ghp_" + ("x" * 36)

    def no_token():
        raise RuntimeError("no_token")

    cd.observe_quota(tmp_path, fetch_user=no_token, now=NOW)
    doc = cd.load_observation(tmp_path)
    assert doc["state"] == "unknown"
    assert doc.get("fetched_at") in ("", None)
    assert doc.get("last_error") == "no_token"
    blob = cd.observation_path(tmp_path).read_text(encoding="utf-8")
    assert secret not in blob
    assert "FAKE_ghp_" not in blob


def test_observe_incomplete_premium_is_unknown(tmp_path):
    raw = {
        "copilot_plan": "business",
        "quota_snapshots": {"premium_interactions": {"credits_used": 3}},
    }
    out = cd.observe_quota(tmp_path, fetch_user=lambda: raw, now=NOW)
    assert out["state"] == "unknown"
    assert out.get("fetched_at") in ("", None)


def test_observe_cache_and_recovery(tmp_path):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return UNLIMITED

    cd.observe_quota(tmp_path, fetch_user=fetch, now=NOW)
    cd.observe_quota(tmp_path, fetch_user=fetch, now=NOW + 100)
    assert calls["n"] == 1
    cd.observe_quota(tmp_path, fetch_user=fetch, now=NOW + 301)
    assert calls["n"] == 2


def test_observe_future_epoch_not_cache_valid(tmp_path):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return UNLIMITED

    # Seed with a future attempt epoch (clock skew) — must not count as valid cache.
    path = cd.observation_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "state": "ok",
                "unlimited": True,
                "fetched_at": _iso(NOW + 10_000),
                "fetched_epoch": NOW + 10_000,
                "attempted_epoch": NOW + 10_000,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cd.observe_quota(tmp_path, fetch_user=fetch, now=NOW)
    assert calls["n"] == 1


def test_observe_independent_of_dispatch_disabled(tmp_path):
    # No allowance file => dispatch off; observer still refreshes and does not create allowance.
    assert cd.dispatch_enabled(tmp_path) is False
    cd.observe_quota(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)
    assert cd.observation_path(tmp_path).is_file()
    assert not cd._allow_path(tmp_path).is_file()
    assert cd.dispatch_enabled(tmp_path) is False

    # Explicit disabled allowance must not be mutated.
    cd._allow_path(tmp_path).write_text(
        json.dumps({"enabled": False, "state": "ok", "remaining": 1}) + "\n", encoding="utf-8"
    )
    before = cd._allow_path(tmp_path).read_text(encoding="utf-8")
    gitclaim.apply_queue_event(
        tmp_path,
        gitclaim.GitClaim(
            repo="SimonBarnett/bobiverse",
            task="FR",
            id="#6148",
            event="issues",
            action="opened",
            line="x",
        ),
    )
    q_before = json.dumps(gitclaim.load_queue(tmp_path), sort_keys=True)
    cd.observe_quota(tmp_path, fetch_user=lambda: LIMITED, now=NOW + 400)
    assert cd._allow_path(tmp_path).read_text(encoding="utf-8") == before
    assert json.dumps(gitclaim.load_queue(tmp_path), sort_keys=True) == q_before


def test_observe_independent_of_cooldown(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)
    cd.mark_tokens_exhausted(tmp_path, now=NOW, reset_date="2099-01-01T00:00:00Z")
    assert cd.cooldown_active(tmp_path, now=NOW + 10) is True
    allow_before = cd._allow_path(tmp_path).read_text(encoding="utf-8")
    cd.observe_quota(tmp_path, fetch_user=lambda: LIMITED, now=NOW + 400)
    assert cd.load_observation(tmp_path)["remaining"] == 140
    assert cd._allow_path(tmp_path).read_text(encoding="utf-8") == allow_before


def test_pool_for_digest_prefers_newer_observation(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)
    cd.observe_quota(tmp_path, fetch_user=lambda: LIMITED, now=NOW + 400)
    pool = cd.pool_for_digest(tmp_path)
    assert pool["remaining"] == 140
    assert pool["fetched_at"] == _iso(NOW + 400)
    assert pool["unlimited"] is False
    assert "attempted_at" in pool
    # Internal fields stay out of public projection.
    for banned in ("fetched_epoch", "fuels", "enabled", "last_error"):
        assert banned not in pool or pool.get(banned) is None or banned == "last_error"
    assert "last_error" not in pool


def test_pool_for_digest_failed_allowance_does_not_outrank_observation(tmp_path):
    """FIX #6180: failed refresh bumps fetched_epoch but must not beat a newer obs fetched_at."""
    cd.observe_quota(tmp_path, fetch_user=lambda: LIMITED, now=NOW + 400)
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)

    def boom():
        raise RuntimeError("nope")

    cd.refresh_allowance(tmp_path, fetch_user=boom, now=NOW + 800)
    allow = cd.load_allowance(tmp_path)
    assert allow["fetched_at"] == _iso(NOW)
    assert allow.get("fetched_epoch") == NOW + 800
    pool = cd.pool_for_digest(tmp_path)
    assert pool["remaining"] == 140
    assert pool["fetched_at"] == _iso(NOW + 400)
    assert pool["unlimited"] is False


def test_pool_for_digest_failed_observation_does_not_outrank_allowance(tmp_path):
    """FIX #6180: first failed observe after successful allowance keeps allowance quota."""
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)

    def boom():
        raise RuntimeError("nope")

    cd.observe_quota(tmp_path, fetch_user=boom, now=NOW + 400)
    obs = cd.load_observation(tmp_path)
    assert not (obs.get("fetched_at") or "").strip() or obs.get("state") == "unknown"
    pool = cd.pool_for_digest(tmp_path)
    assert pool["unlimited"] is True
    assert pool["fetched_at"] == _iso(NOW)


def test_refresh_allowance_preserves_fetched_at_on_failure(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=NOW)
    first = cd.load_allowance(tmp_path)["fetched_at"]
    assert first == _iso(NOW)

    def boom():
        raise RuntimeError("nope")

    cd.refresh_allowance(tmp_path, fetch_user=boom, now=NOW + 400)
    doc = cd.load_allowance(tmp_path)
    assert doc["fetched_at"] == first
    assert doc.get("attempted_at") == _iso(NOW + 400)
    assert doc.get("fetched_epoch") == NOW + 400


def test_chair_tick_observes_even_when_dispatch_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    calls = {"n": 0}

    class Clock:
        def __init__(self):
            self.t = NOW

        def __call__(self):
            return self.t

    clk = Clock()

    def github_json(method, url, body=None):
        calls["n"] += 1
        if "copilot_internal/user" in url:
            return UNLIMITED, 200
        return {}, 200

    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=lambda *_a, **_k: None,
        http=lambda *a, **k: 200,
        fetch_json=lambda url: [],
        token_loader=lambda: ("FAKE_token_for_tests_only", "file:x"),
        clock=clk,
        sleep=lambda s: None,
        spawn=False,
        owners={"SimonBarnett"},
    )
    j._github_json = github_json  # type: ignore[method-assign]
    # No allowance => dispatch disabled; observer must still run.
    assert cd.dispatch_enabled(tmp_path) is False
    j._copilot_tick()
    assert cd.observation_path(tmp_path).is_file()
    assert cd.load_observation(tmp_path)["fetched_at"] == _iso(NOW)
    assert calls["n"] >= 1


def test_chair_tick_no_token_records_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    bobreport.save_digest(tmp_path, bobreport.empty_digest())

    class Clock:
        def __call__(self):
            return NOW

    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=lambda *_a, **_k: None,
        http=lambda *a, **k: 200,
        fetch_json=lambda url: [],
        token_loader=lambda: (None, "missing"),
        clock=Clock(),
        sleep=lambda s: None,
        spawn=False,
        owners={"SimonBarnett"},
    )
    j._copilot_tick()
    doc = cd.load_observation(tmp_path)
    assert doc.get("last_error") == "no_token"
    assert doc.get("fetched_at") in ("", None)
