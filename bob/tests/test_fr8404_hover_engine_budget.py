"""FR #8404: update-hover-engine must not scan every process or use a 15s digest GET."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOVER = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
IRC = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def _fn(text: str, name: str) -> str:
    start = text.find(f"function {name}")
    assert start >= 0, name
    nxt = text.find("\nfunction ", start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


def test_fr8404_live_grok_queries_grok_exe_only():
    body = _fn(HOVER.read_text(encoding="utf-8"), "Get-BobLiveGrokAgents")
    assert 'Get-CimInstance Win32_Process -Filter "Name=\'grok.exe\'"' in body
    assert "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |" not in body
    assert "$parentByPid" in body


def test_fr8404_digest_http_honors_engine_timeout_env():
    body = _fn(IRC.read_text(encoding="utf-8"), "Read-BobReportDigestHttp")
    assert "BOB_DIGEST_HTTP_TIMEOUT_SEC" in body
    assert "TimeoutSec $timeoutSec" in body


def test_fr8404_engine_hover_sets_short_digest_timeout():
    watch = WATCH.read_text(encoding="utf-8")
    start = watch.find("-Name 'update-hover-engine'")
    assert start >= 0
    window = watch[start:start + 1800]
    assert "BOB_DIGEST_HTTP_TIMEOUT_SEC = '8'" in window
    assert "Get-BobTrayHover" in window
    assert "Remove-Item Env:\\BOB_DIGEST_HTTP_TIMEOUT_SEC" in window
    assert "$prevDigestTimeout" in window
