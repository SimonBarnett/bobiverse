"""FR #5032: stale peer Grok % must not look live; engine digest heartbeat must POST;
402 marks weekly=0; no 'Grok accounts' heading.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import bob_worker as bw

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr5032_tray_digest_timer_redots_dialogs_and_logs_failures():
    w = _txt(WATCH)
    # Locate the FR #5032 / trayDigestTimer setup + Action (MessageData precedes Register).
    assert "trayDigestTimer" in w
    assert "FR #5032" in w
    start = w.index("$script:trayDigestTimer = New-Object System.Timers.Timer")
    block = w[start : start + 4500]
    assert "BobTrayDialogs.ps1" in block
    assert ". $msg.Dialogs" in block
    assert "Test-BobTrayEngineMode" in block
    assert "Write-BobIrcStatus" in block
    assert "tray-lifecycle.log" in block
    assert "WARN trayDigestTimer" in block
    # Must not rely solely on missing flat scripts\\Write-BobIrcStatus.ps1
    assert "Get-BobIrc.ps1" in block or "IrcPs" in block


def test_fr5032_digest_post_failures_are_logged():
    irc = _txt(IRC)
    assert "FR #5032" in irc
    assert "digest-webhook.log" in irc
    assert "Send-BobDigestWebhookIfChanged failed" in irc or "digest POST failed" in irc


def test_fr5032_expand_weekly_rows_carry_lastseen_and_out_of_tokens():
    h = _txt(HOVER)
    assert "out_of_tokens" in h
    assert "lastSeen" in h[h.index("function Expand-BobReportDigestView") :]
    assert "Format-BobTrayFuelStaleAge" in h
    assert "fuel_stale" in h
    assert "fuelStaleAfter" in h
    assert "digest-lastSeen-stale" in h


def test_fr5032_no_grok_accounts_heading():
    w = _txt(WATCH)
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "Title 'Grok accounts'" not in sec
    assert 'Title "Grok accounts"' not in sec
    assert "Title 'Cursor'" not in sec and 'Title "Cursor"' not in sec
    cs = _txt(STATUS_CS)
    render = cs[cs.index("public int Render") : cs.index("protected override void OnPaint")]
    assert 'Section(g, y, "Grok accounts"' not in render
    assert 'Section(g, y, "Cursor"' not in render
    if DOCS.is_file():
        d = _txt(DOCS)
        assert "Cursor pools first" not in d
        assert "FR #5032" in d
        assert 'no\n"Grok accounts" heading' in d or 'no "Grok accounts" heading' in d


def test_fr5032_post_digest_out_of_fuel_includes_weekly_zero():
    logs: list[str] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        body = json.loads(req.data.decode("utf-8"))
        assert body.get("weekly") == 0
        assert body.get("out_of_tokens") is True
        assert body.get("status") == "out_of_fuel"
        assert body.get("id")

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        ok = bw.post_digest_out_of_fuel(
            machine="win-mpre8vi4u6u",
            nick="win-mpre8vi4u6u-1",
            evidence="402 Payment Required",
            url="https://example.test/bob/v1/report",
            log=logs.append,
        )
    assert ok is True


def test_fr5032_post_digest_out_of_fuel_logs_failure():
    logs: list[str] = []

    def boom(*a, **k):  # noqa: ARG001
        raise bw.urllib.error.URLError("down")

    with mock.patch("urllib.request.urlopen", boom):
        ok = bw.post_digest_out_of_fuel(
            machine="flamingo",
            evidence="402",
            url="https://example.test/bob/v1/report",
            log=logs.append,
        )
    assert ok is False
    assert any("digest POST failed" in m or "post_digest_out_of_fuel failed" in m for m in logs)
