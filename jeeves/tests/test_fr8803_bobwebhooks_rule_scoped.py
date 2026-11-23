"""FR #8803: Install-BobWebhooks only manages Bob* rules; never retargets websockets or www."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")

WS_RULE_WSIRC = """        <rule name="WsircWebSocket7999" stopProcessing="true">
          <match url="^wsirc(/.*)?$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:8097/wsirc{R:1}" />
        </rule>
"""
WS_RULE_IRC = """        <rule name="IrcWebSocket7999" stopProcessing="true">
          <match url="^irc(/.*)?$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:8097/{R:1}" />
        </rule>
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_webconfig() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
{WS_RULE_WSIRC}{WS_RULE_IRC}        <rule name="BobReportWebhook" stopProcessing="true">
          <match url="^bob/v1/report$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/report" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"""


def _run(site: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    assert PS
    args = [
        PS,
        "-NoProfile",
        "-File",
        str(SCRIPT),
        "-PhysicalPath",
        str(site),
        "-Backend",
        "http://127.0.0.1:7700",
        *extra,
    ]
    return subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)


def _ws_snippets(cfg: str) -> tuple[str, str]:
    m1 = re.search(r'(?s)<rule name="WsircWebSocket7999".*?</rule>', cfg)
    m2 = re.search(r'(?s)<rule name="IrcWebSocket7999".*?</rule>', cfg)
    assert m1 and m2, cfg
    return m1.group(0), m2.group(0)


@NEED_PS
def test_fr8803_websocket_rules_byte_identical_and_models_added(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    marker = site / "operator-www.txt"
    marker.write_text("do-not-touch\n", encoding="utf-8")
    cfg_path = site / "web.config"
    cfg_path.write_text(_fixture_webconfig(), encoding="utf-8")
    before_ws = _ws_snippets(cfg_path.read_text(encoding="utf-8"))

    r1 = _run(site)
    assert r1.returncode == 0, r1.stdout + "\n" + r1.stderr
    body1 = cfg_path.read_text(encoding="utf-8")
    after_ws = _ws_snippets(body1)
    assert after_ws == before_ws, "websocket rules must stay byte-identical"
    assert "127.0.0.1:8097" in body1
    assert body1.count("127.0.0.1:7700") >= 1
    assert 'name="BobModelsWebhook"' in body1
    models = re.search(r'(?s)<rule name="BobModelsWebhook".*?</rule>', body1)
    # FR #9224: POST refresh must rewrite; PUT/PATCH stay blocked (GET|HEAD|POST).
    assert models and 'REQUEST_METHOD' in models.group(0) and 'GET|HEAD|POST' in models.group(0)
    assert 'name="BobJeevesAppliance"' in body1
    assert marker.read_text(encoding="utf-8") == "do-not-touch\n"
    assert not (site / "site.css").is_file(), "default run must not publish www"
    assert (site / "ROLLBACK-BobWebhooks.ps1").is_file()
    # FR #8887: web.config backup lives under sibling _backup-www-<leaf>, not inside the site.
    assert not list(site.glob("*.bak")) and not list(site.rglob("*.bak")), (
        "no *.bak under web root"
    )
    bak = site.parent / ("_backup-www-" + site.name) / "web.config"
    assert bak.is_file(), f"off-root web.config backup required at {bak}"

    sha1 = _sha(cfg_path)
    r2 = _run(site)
    assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
    assert _sha(cfg_path) == sha1, "second run must produce no web.config diff"
    assert "already current" in (r2.stdout + r2.stderr).lower() or sha1 == _sha(cfg_path)
    assert _ws_snippets(cfg_path.read_text(encoding="utf-8")) == before_ws


@NEED_PS
def test_fr8803_script_has_no_blanket_port_replace():
    text = SCRIPT.read_text(encoding="ascii")
    assert "PublishWww" in text
    assert "ROLLBACK-BobWebhooks" in text or "Write-BobWebhooksRollback" in text
    assert "Set-BobOwnedRewriteRule" in text
    # The destructive blanket replace must be gone.
    assert "-replace '127\\.0\\.0\\.1:\\d+'" not in text
    assert '127\\.0\\.0\\.1:\\d+' not in text or "never blanket" in text.lower()


def test_fr8803_ascii_bomless():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("ascii")
