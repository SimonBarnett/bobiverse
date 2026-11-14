"""FR #6141: ear owns digest fuel publish; tray fuel POST off.

Tray Write-BobIrcStatus gathers peer JSON for paint but does not POST fuel merges
unless capture mode or -PostDigestWebhook. Ear publish_local_peer_fuel POSTs on
fingerprint change / heartbeat. Worker out-of-fuel POST still works.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bobreport
import bobstat

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
IRC = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6141_write_bob_irc_status_skips_fuel_post_by_default():
    irc = _txt(IRC)
    assert "FR #6141" in irc
    start = irc.index("function Write-BobIrcStatus")
    nxt = irc.find("\nfunction ", start + 10)
    block = irc[start : nxt if nxt > 0 else start + 40000]
    assert "PostDigestWebhook" in block
    assert "Send-BobDigestWebhookIfChanged" in block
    assert "Get-BobDigestWebhookCapturePath" in block
    assert "$PostDigestWebhook -or" in block or "if ($PostDigestWebhook" in block
    # Default path is gated: only POST when opted in or capture (FR #6141).
    assert "ear publish_local_peer_fuel" in block or "ear owns fuel" in block.lower() or "FR #6141" in block


def test_fr6141_watch_tray_does_not_opt_in_fuel_post():
    w = _txt(WATCH)
    assert "-PostDigestWebhook" not in w
    assert "Write-BobIrcStatus" in w


def test_fr6141_sync_after_pull_no_longer_posts():
    irc = _txt(IRC)
    start = irc.index("function Sync-BobDigestWebhookAfterBobiversePull")
    block = irc[start : start + 800]
    assert "FR #6141" in block
    assert "Send-BobDigestWebhookIfChanged" not in block or block.index("return") < block.find("Send-BobDigestWebhookIfChanged")
    # Early return: no Send call on the live path
    assert "return" in block
    assert "ear owns fuel" in block.lower() or "publish_local_peer_fuel" in block


def test_fr6141_ear_tick_calls_publish_local_peer_fuel():
    src = _txt(IRC_AGENT)
    assert "FR #6141" in src
    assert "publish_local_peer_fuel" in src
    assert "_maybe_publish_digest_fuel" in src


def test_fr6141_publish_posts_on_remaining_change(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    mid = "redqueen"
    # FR #7289: ear does not fetch Cursor; isolate fingerprint from live xAI
    # keep-last-good stamps (remaining_last_attempt_at) so skip vs change is peer-only.
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda: None)
    monkeypatch.setattr(
        bobreport, "enrich_peer_keep_last_good_xai_weekly", lambda peer, error=None: peer
    )
    monkeypatch.setattr(bobreport, "pool_fetch_due", lambda *a, **k: False)
    peer = {
        "ok": True,
        "id": mid,
        "online": True,
        "status": "operational",
        "weekly": 80,
        "weekly_known": True,
        "remaining_pct": 42,
        "pcent": {"grok-chat": 42, "cursor-models": 10},
        "cursor_pools": [
            {"group_id": "grok-chat", "remaining_pct": 42, "machine_id": mid},
        ],
        "lastSeen": "2026-11-07T12:00:00Z",
    }
    bobstat.write_peer(home, peer)

    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        body = json.loads(req.data.decode("utf-8"))
        posted.append(body)

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_local_peer_fuel(
            home, mid, force=True, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert len(posted) == 1
    body = posted[0]
    assert body.get("op") == "merge"
    assert body.get("machine") == mid
    assert body.get("weekly") == 80
    assert body.get("pcent", {}).get("grok-chat") == 42
    assert isinstance(body.get("cursor_pools"), list)
    row0 = body["cursor_pools"][0]
    rem = row0.get("remaining_pct", row0.get("remaining"))
    assert rem == 42

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code2 = bobreport.publish_local_peer_fuel(
            home, mid, force=False, url="https://example.test/bob/v1/report", now=1.0
        )
    assert code2 is None
    assert len(posted) == 1

    peer2 = dict(peer)
    peer2["remaining_pct"] = 41
    peer2["pcent"] = {"grok-chat": 41, "cursor-models": 10}
    bobstat.write_peer(home, peer2)
    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code3 = bobreport.publish_local_peer_fuel(
            home, mid, force=False, url="https://example.test/bob/v1/report", now=2.0
        )
    assert code3 == 204
    assert len(posted) == 2
    assert posted[1]["pcent"]["grok-chat"] == 41


def test_fr6141_out_of_fuel_worker_post_still_works():
    """Regression pin: worker post_digest_out_of_fuel helper still present."""
    import bob_worker as bw

    assert callable(getattr(bw, "post_digest_out_of_fuel", None))
