# FR #6903: Install-BobWebhooks.ps1 rewrites /jeeves to bobcallback (idempotent).
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"

_EXISTING = (
    "BobReportWebhook",
    "BobDigestWebhook",
    "BobGitWebhook",
    "BobIntakeWebhook",
    "BobJiraWebhook",
    "BobHoursWebhook",
)


def _run_install(physical: Path, *, what_if: bool = False, backend: str = "http://127.0.0.1:7700") -> subprocess.CompletedProcess:
    args = [
        "pwsh",
        "-NoProfile",
        "-File",
        str(SCRIPT),
        "-PhysicalPath",
        str(physical),
        "-Backend",
        backend,
    ]
    if what_if:
        args.append("-WhatIf")
    return subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)


def test_fr6903_script_pins_jeeves_rule_and_ascii():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("ascii")
    assert 'name="BobJeevesAppliance"' in text
    assert 'url="^jeeves(/.*)?$"' in text
    assert "jeeves{R:1}" in text
    assert text.count("BobJeevesAppliance") >= 2  # fresh template + idempotent insert


def test_fr6903_generated_webconfig_idempotent(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    r1 = _run_install(site)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    cfg = site / "web.config"
    assert cfg.is_file()
    body1 = cfg.read_text(encoding="utf-8")
    assert body1.count('name="BobJeevesAppliance"') == 1
    for name in _EXISTING:
        assert body1.count(f'name="{name}"') == 1, name
    assert 'url="^jeeves(/.*)?$" ignoreCase="true"' in body1
    assert "http://127.0.0.1:7700/jeeves{R:1}" in body1

    r2 = _run_install(site)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    body2 = cfg.read_text(encoding="utf-8")
    assert body2.count('name="BobJeevesAppliance"') == 1
    for name in _EXISTING:
        assert body2.count(f'name="{name}"') == 1, name


def test_fr6903_jeeves_rule_does_not_match_bob_v1_or_docs():
    text = SCRIPT.read_text(encoding="ascii")
    m = re.search(
        r'<rule name="BobJeevesAppliance"[^>]*>\s*<match url="([^"]+)"',
        text,
    )
    assert m, "BobJeevesAppliance match missing"
    pat = m.group(1)
    rx = re.compile(pat, re.IGNORECASE)
    assert rx.match("jeeves")
    assert rx.match("jeeves/")
    assert rx.match("jeeves/login")
    assert not rx.match("bob/v1/report")
    assert not rx.match("bob/v1/intake")
    assert not rx.match("docs/webhooks")
    assert not rx.match("docs/webhooks/index.html")


def test_fr6903_whatif_does_not_write(tmp_path: Path):
    site = tmp_path / "irc-ntsa-whatif"
    site.mkdir()
    r = _run_install(site, what_if=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WhatIf would write" in (r.stdout + r.stderr)
    assert not (site / "web.config").exists()


def test_fr6903_inserts_into_existing_six_rule_config(tmp_path: Path):
    """Idempotent insert when an older web.config lacks BobJeevesAppliance."""
    site = tmp_path / "irc-ntsa-old"
    site.mkdir()
    old = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="BobReportWebhook" stopProcessing="true">
          <match url="^bob/v1/report$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/report" />
        </rule>
        <rule name="BobDigestWebhook" stopProcessing="true">
          <match url="^bob/v1/digest$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/digest" />
        </rule>
        <rule name="BobGitWebhook" stopProcessing="true">
          <match url="^bob/v1/git$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/git" />
        </rule>
        <rule name="BobIntakeWebhook" stopProcessing="true">
          <match url="^bob/v1/intake(.*)" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/intake{R:1}" />
        </rule>
        <rule name="BobJiraWebhook" stopProcessing="true">
          <match url="^bob/v1/jira(.*)" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/jira{R:1}" />
        </rule>
        <rule name="BobHoursWebhook" stopProcessing="true">
          <match url="^bob/v1/hours(.*)" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/hours{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"""
    (site / "web.config").write_text(old, encoding="utf-8")
    r = _run_install(site)
    assert r.returncode == 0, r.stdout + r.stderr
    body = (site / "web.config").read_text(encoding="utf-8")
    assert body.count('name="BobJeevesAppliance"') == 1
    for name in _EXISTING:
        assert body.count(f'name="{name}"') == 1, name
