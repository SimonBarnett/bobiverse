"""FR #6760 / FR-12: appliance /pools machine rows from digest xai_weekly."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _opener_with_cookies():
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def _write_digest(digest: Path, doc: dict) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    (digest / "digest.json").write_text(json.dumps(doc), encoding="utf-8")


def test_fr6760_render_42_percent():
    html = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {
                    "id": "marchhare",
                    "remaining_pct": 42,
                    "fuel_stale": False,
                    "reset_label": "2 days, 3 hours",
                }
            ],
        }
    )
    assert "42%" in html
    assert "out of tokens" not in html.lower()
    assert "[stale]" not in html
    assert "n/a" not in html
    assert "2 days, 3 hours" in html
    assert "marchhare" in html
    assert "No pool readings" not in html


def test_fr6760_render_zero_out_of_tokens():
    html = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {
                    "id": "flamingo",
                    "remaining_pct": 0,
                    "fuel_stale": False,
                    "reset_label": None,
                }
            ],
        }
    )
    assert "0%" in html
    assert "out of tokens" in html.lower()
    assert "[stale]" not in html


def test_fr6760_render_stale_hides_percent():
    html = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {
                    "id": "ionos",
                    "remaining_pct": 42,
                    "fuel_stale": True,
                    "reset_label": "1 hour, 2 minutes",
                }
            ],
        }
    )
    assert "[stale]" in html
    assert "42%" not in html
    assert "out of tokens" not in html.lower()


def test_fr6760_render_null_na():
    html = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {
                    "id": "redqueen",
                    "remaining_pct": None,
                    "fuel_stale": False,
                    "reset_label": None,
                }
            ],
        }
    )
    assert "n/a" in html
    assert "42%" not in html
    assert "[stale]" not in html


def test_fr6760_render_empty_and_escape_and_no_cursor_bars():
    empty = http._render_pools_html({"ok": True, "machines": []})
    assert "No pool readings" in empty
    hostile = http._render_pools_html(
        {
            "ok": True,
            "machines": [
                {
                    "id": "<script>x</script>",
                    "remaining_pct": 10,
                    "fuel_stale": False,
                    "reset_label": "<b>reset</b>",
                }
            ],
        }
    )
    assert "<script>" not in hostile
    assert "&lt;script&gt;" in hostile or "&#" in hostile
    assert "<b>reset</b>" not in hostile
    low = hostile.lower()
    assert "grok-chat" not in low
    assert "high-cost-models" not in low
    assert "class=\"bar" not in low
    assert "<svg" not in low
    assert 'href="/pools"' in empty or "Pools" in empty
    assert 'href="/"' in empty
    assert 'href="/status"' in empty
    assert 'href="/logout"' in empty



def test_fr6760_provider_row_rules(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
    future = (now + timedelta(days=2, hours=3)).isoformat().replace("+00:00", "Z")
    past = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    old_fetch = (now - timedelta(seconds=200)).isoformat().replace("+00:00", "Z")
    fresh_fetch = (now - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    _write_digest(
        digest,
        {
            "roster_machine_ids": ["MarchHare", "flamingo", "IONOS", "nullmeter"],
            "machines": {
                "marchhare": {
                    "xai_weekly": {
                        "remaining_pct": 42,
                        "fresh": True,
                        "fetched_at": fresh_fetch,
                        "age_s": 10,
                        "period_end": future,
                    }
                },
                "flamingo": {
                    "xai_weekly": {
                        "remaining_pct": 0,
                        "fresh": True,
                        "fetched_at": fresh_fetch,
                        "age_s": 5,
                        "period_end": future,
                    }
                },
                "ionos": {
                    "xai_weekly": {
                        "remaining_pct": 42,
                        "fresh": False,
                        "fetched_at": fresh_fetch,
                        "age_s": 5,
                        "period_end": future,
                    }
                },
                "nullmeter": {"xai_weekly": None},
                "extra": {
                    "xai_weekly": {
                        "remaining_pct": True,
                        "fresh": True,
                        "fetched_at": old_fetch,
                        "period_end": past,
                    }
                },
            },
            "weekly": {"marchhare": 99},
            "cursor_pools": {"grok-chat": {"remaining_pct": 7}},
            "pcent": {"marchhare": 11},
        },
    )
    view = js.api_get_pools(
        chair, client_ip="10.0.0.2", digest_home=digest, now=now.timestamp()
    )
    assert view["ok"] is True
    ids = [m["id"] for m in view["machines"]]
    assert ids == ["marchhare", "flamingo", "ionos", "nullmeter"]
    by = {m["id"]: m for m in view["machines"]}
    assert by["marchhare"]["remaining_pct"] == 42
    assert by["marchhare"]["fuel_stale"] is False
    assert by["marchhare"]["reset_label"]
    assert "day" in by["marchhare"]["reset_label"]
    assert by["flamingo"]["remaining_pct"] == 0
    assert by["flamingo"]["fuel_stale"] is False
    assert by["ionos"]["fuel_stale"] is True
    assert by["ionos"]["remaining_pct"] == 42
    assert by["nullmeter"]["remaining_pct"] is None
    assert by["nullmeter"]["fuel_stale"] is False
    blob = json.dumps(view)
    assert "cursor_pools" not in blob
    assert "grok-chat" not in blob
    assert "weekly" not in blob or '"weekly"' not in blob


def test_fr6760_provider_stale_missing_age_and_empty_digest(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
    _write_digest(
        digest,
        {
            "machines": {
                "a": {
                    "xai_weekly": {
                        "remaining_pct": 9,
                        "fresh": True,
                        # no age_s / fetched_at -> stale
                    }
                }
            }
        },
    )
    view = js.api_get_pools(
        chair, client_ip="127.0.0.1", digest_home=digest, now=now.timestamp()
    )
    assert view["machines"][0]["fuel_stale"] is True
    assert view["machines"][0]["remaining_pct"] == 9

    empty = tmp_path / "empty"
    empty.mkdir()
    missing = js.api_get_pools(
        chair, client_ip="127.0.0.1", digest_home=empty, now=now.timestamp()
    )
    assert missing["ok"] is True
    assert missing["machines"] == []


def test_fr6760_http_login_and_authed_pools(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
    future = (now + timedelta(hours=5, minutes=10)).isoformat().replace("+00:00", "Z")
    fetch = (now - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    _write_digest(
        digest,
        {
            "roster_machine_ids": ["marchhare"],
            "machines": {
                "marchhare": {
                    "xai_weekly": {
                        "remaining_pct": 42,
                        "fresh": True,
                        "fetched_at": fetch,
                        "age_s": 5,
                        "period_end": future,
                    }
                }
            },
        },
    )
    port = _free_port()
    srv = http.start_settings_http(
        chair,
        bind="127.0.0.1",
        port=port,
        digest_home=digest,
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    opener, _jar = _opener_with_cookies()
    try:
        with urllib.request.urlopen(base + "/pools", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
        assert "password" in body.lower()

        try:
            urllib.request.urlopen(base + "/api/pools", timeout=5)
            assert False, "expected unauth api reject"
        except urllib.error.HTTPError as e:
            assert e.code in (401, 403)
            err = json.loads(e.read().decode("utf-8"))
            assert err.get("ok") is False
            assert "unauthorized" in str(err.get("error") or "").lower()

        login_req = urllib.request.Request(
            base + "/api/login",
            data=json.dumps(
                {"username": "ApplianceAdmin", "password": "FAKE_ok"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with opener.open(login_req, timeout=5) as resp:
            login = json.loads(resp.read().decode("utf-8"))
        tok = login["session_token"]

        with opener.open(base + "/pools", timeout=5) as resp:
            page = resp.read().decode("utf-8")
        assert "42%" in page
        assert "marchhare" in page
        assert "password" not in page.lower() or "type=\"password\"" not in page.lower()

        br = urllib.request.Request(
            base + "/api/pools",
            headers={"Authorization": f"Bearer {tok}"},
            method="GET",
        )
        with urllib.request.urlopen(br, timeout=5) as resp:
            api = json.loads(resp.read().decode("utf-8"))
        assert api.get("ok") is True
        assert api["machines"][0]["remaining_pct"] == 42
        assert "token" not in json.dumps(api).lower() or "session" not in json.dumps(
            api
        )

        with opener.open(base + "/", timeout=5) as resp:
            settings = resp.read().decode("utf-8")
        with opener.open(base + "/status", timeout=5) as resp:
            status = resp.read().decode("utf-8")
        assert 'href="/pools"' in settings
        assert 'href="/pools"' in status
    finally:
        http.stop_settings_http(srv)
