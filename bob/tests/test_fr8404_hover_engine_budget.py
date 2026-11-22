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
    text = HOVER.read_text(encoding="utf-8")
    body = _fn(text, "Get-BobLiveGrokAgents")
    # FR #8404: grok.exe only. FR #8891: timed WMI (not bare Get-CimInstance).
    assert "Name='grok.exe'" in body
    assert "Get-BobWin32ProcessTimed" in body
    assert "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |" not in body
    assert "$parentByPid" in body
    helper = _fn(text, "Get-BobWin32ProcessTimed")
    assert "EnumerationOptions" in helper
    assert "Timeout" in helper


def test_fr8404_digest_http_honors_engine_timeout_env():
    body = _fn(IRC.read_text(encoding="utf-8"), "Read-BobReportDigestHttp")
    assert "BOB_DIGEST_HTTP_TIMEOUT_SEC" in body
    assert "TimeoutSec $timeoutSec" in body


def test_fr8404_engine_hover_sets_short_digest_timeout():
    watch = WATCH.read_text(encoding="utf-8")
    start = watch.find("# FR #8404: keep the digest GET inside the 45s step budget.")
    assert start >= 0
    window = watch[start:start + 1800]
    assert "BOB_DIGEST_HTTP_TIMEOUT_SEC = '8'" in window
    assert "Get-BobTrayHover" in window
    assert "$prevDigestTimeout" in window
    assert "Remove-Item Env:\\BOB_DIGEST_HTTP_TIMEOUT_SEC" in window
    # $ps.Stop() on timeout skips finally inside the child scriptblock.
    assign_at = window.find("BOB_DIGEST_HTTP_TIMEOUT_SEC = '8'")
    invoke_at = window.find("-Name 'update-hover-engine'", assign_at)
    assert 0 <= assign_at < invoke_at
    body_at = window.find("-Body {", invoke_at)
    assert body_at > invoke_at
    body = window[body_at:body_at + 900]
    assert "BOB_DIGEST_HTTP_TIMEOUT_SEC = '8'" not in body
