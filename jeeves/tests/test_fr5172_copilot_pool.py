"""FR #5172: live Copilot allowance, webhook ensure on chair, digest pool."""
from __future__ import annotations

import bobreport
import chair_health as ch
import copilot_dispatch as cd
import gitclaim


UNLIMITED = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-11-01T00:00:00.000Z",
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


def test_parse_unlimited_limited_unknown():
    u = cd.parse_user_quota(UNLIMITED)
    assert u["unlimited"] is True and u["state"] == "ok" and u["used"] == 39
    lim = cd.parse_user_quota(
        {
            "quota_snapshots": {
                "premium_interactions": {
                    "unlimited": False,
                    "remaining": 4,
                    "percent_remaining": 10,
                    "credits_used": 1,
                }
            }
        }
    )
    assert lim["state"] == "ok"
    zero = cd.parse_user_quota(
        {
            "quota_snapshots": {
                "premium_interactions": {
                    "unlimited": False,
                    "remaining": 0,
                    "percent_remaining": 0,
                    "credits_used": 9,
                }
            }
        }
    )
    assert zero["state"] == "exhausted"
    assert cd.parse_user_quota({"nope": 1})["state"] == "unknown"
    assert cd.parse_user_quota(None)["state"] == "unknown"


def test_dispatch_on_off(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=1.0)
    assert cd.has_allowance(tmp_path) is True
    cd.refresh_allowance(
        tmp_path,
        fetch_user=lambda: {
            "quota_snapshots": {
                "premium_interactions": {
                    "unlimited": False,
                    "remaining": 0,
                    "percent_remaining": 0,
                }
            }
        },
        now=400.0,
    )
    assert cd.has_allowance(tmp_path) is False
    cd.refresh_allowance(tmp_path, fetch_user=lambda: {"bad": True}, now=800.0)
    assert cd.has_allowance(tmp_path) is True  # unknown -> try


def test_tasks_quota_stops_dispatch(tmp_path):
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=1.0)
    cd.record_api_result(tmp_path, {"status": 403, "message": "Copilot allowance exhausted"})
    assert cd.has_allowance(tmp_path) is False


def test_ensure_called_startup_and_tick(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "SimonBarnett/bobiverse")
    calls = []

    def list_missing(_repo):
        calls.append("list")
        return []

    created = []
    r = cd.ensure_served_webhooks(
        ["SimonBarnett/bobiverse"],
        list_hooks=list_missing,
        create=lambda b: created.append(b),
        patch=lambda *_a, **_k: None,
    )
    assert r[0]["action"] == "create" and created

    repaired = []
    r = cd.ensure_served_webhooks(
        ["SimonBarnett/bobiverse"],
        list_hooks=lambda _r: [
            {"id": 1, "active": True, "events": ["push"], "config": {"url": cd.GIT_HOOK_URL}}
        ],
        create=lambda b: None,
        patch=lambda hid, body: repaired.append((hid, body)),
    )
    assert r[0]["action"] == "repair" and repaired

    ok = []
    r = cd.ensure_served_webhooks(
        ["SimonBarnett/bobiverse"],
        list_hooks=lambda _r: [
            {
                "id": 2,
                "active": True,
                "events": list(cd.REQUIRED_HOOK_EVENTS),
                "config": {"url": cd.GIT_HOOK_URL},
            }
        ],
        create=lambda b: ok.append("create"),
        patch=lambda *_a, **_k: ok.append("patch"),
    )
    assert r[0]["action"] == "ok" and ok == []

    stalls = []
    r = cd.ensure_served_webhooks(
        ["SimonBarnett/bobiverse"],
        list_hooks=lambda _r: (_ for _ in ()).throw(PermissionError("no")),
        create=lambda b: None,
        patch=lambda *_a, **_k: None,
        file_stall=lambda **kw: stalls.append(kw),
    )
    assert r[0]["action"] == "stall" and stalls

    class Clock:
        def __init__(self):
            self.t = 10_000.0

        def __call__(self):
            return self.t

    clk = Clock()
    logs = []
    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=logs.append,
        http=lambda *a, **k: 200,
        fetch_json=lambda url: [],
        token_loader=lambda: ("TOK", "file:x"),
        clock=clk,
        sleep=lambda s: None,
        spawn=False,
        owners={"SimonBarnett"},
    )
    clk.t += ch.FIRST_WEBHOOK_ENSURE_DELAY_S + 1
    j.tick()
    assert any("webhook-ensure" in ln for ln in logs)
    logs.clear()
    clk.t += ch.WEBHOOK_ENSURE_S + 1
    j.tick()
    assert any("webhook-ensure" in ln for ln in logs)


def test_digest_includes_copilot(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    cd.refresh_allowance(tmp_path, fetch_user=lambda: UNLIMITED, now=1.0)
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    obj = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert "copilot" in obj
    assert obj["copilot"]["state"] in ("ok", "unknown", "exhausted")
    assert obj["copilot"]["unlimited"] is True


def test_no_cache_does_not_steal_queue(tmp_path):
    gitclaim.apply_queue_event(
        tmp_path,
        gitclaim.GitClaim(
            repo="SimonBarnett/bobiverse",
            task="FR",
            id="#1",
            event="issues",
            action="opened",
            line="x",
        ),
    )
    assert cd.has_allowance(tmp_path) is False
    assert any(r.get("id") == "#1" for r in gitclaim.load_unaccepted(tmp_path))
