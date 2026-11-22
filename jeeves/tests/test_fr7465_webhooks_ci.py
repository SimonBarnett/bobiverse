"""FR #7465: webhooks CI is separate from the Jeeves service build."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import REPO

import jeeves_webhooks_ci as kit

SERVICE = REPO / ".github" / "workflows" / "build-jeeves.yml"
WEB = REPO / ".github" / "workflows" / "build-jeeves-webhooks.yml"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")
DUP_STATIC = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <staticContent>
      <mimeMap fileExtension=".webp" mimeType="image/webp" />
    </staticContent>
    <staticContent>
      <mimeMap fileExtension=".ico" mimeType="image/x-icon" />
    </staticContent>
  </system.webServer>
</configuration>
"""


def test_fr7465_path_filters_split_www_from_service():
    service = kit.workflow_paths(SERVICE.read_text(encoding="utf-8"), "pull_request")
    hooks = kit.workflow_paths(WEB.read_text(encoding="utf-8"), "pull_request")
    assert "jeeves/**" in service
    assert "!jeeves/www/**" in service
    assert "jeeves/www/**" in hooks
    assert "jeeves/scripts/Install-BobWebhooks.ps1" in hooks
    www_only = ["jeeves/www/irc-ntsa/index.html"]
    service_only = ["common/scripts/jeeves_main.py"]
    assert kit.workflow_runs(hooks, www_only)
    assert not kit.workflow_runs(service, www_only)
    assert kit.workflow_runs(service, service_only)
    assert not kit.workflow_runs(hooks, service_only)
    assert "build-jeeves" in SERVICE.read_text(encoding="utf-8")
    text = WEB.read_text(encoding="utf-8")
    assert "Build-Jeeves.ps1" not in text
    assert "pyinstaller" not in text.lower()


def test_fr7460_duplicate_staticcontent_fails_webhooks_check(tmp_path: Path):
    cfg = tmp_path / "web.config"
    cfg.write_text(DUP_STATIC, encoding="utf-8")
    with pytest.raises(SystemExit, match="duplicate web.config"):
        kit.assert_web_config(cfg)


def test_fr7465_single_section_config_passes(tmp_path: Path):
    cfg = tmp_path / "web.config"
    cfg.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<configuration><system.webServer>
  <rewrite><rules></rules></rewrite>
  <staticContent><mimeMap fileExtension=".ico" mimeType="image/x-icon" /></staticContent>
  <security>
    <requestFiltering allowDoubleEscaping="true">
      <fileExtensions allowUnlisted="true">
        <add fileExtension=".bak" allowed="false" />
      </fileExtensions>
      <denyUrlSequences>
        <add sequence="_backup-" />
        <add sequence=".bak/" />
      </denyUrlSequences>
    </requestFiltering>
  </security>
</system.webServer></configuration>
""",
        encoding="utf-8",
    )
    kit.assert_web_config(cfg)


@NEED_PS
def test_fr7465_site_kit_rollback_restores_tree(tmp_path: Path):
    site = tmp_path / "site"
    site.mkdir()
    marker = site / "keep.txt"
    marker.write_text("before", encoding="ascii")
    www = tmp_path / "www"
    www.mkdir()
    (www / "index.html").write_text("<html></html>", encoding="ascii")
    env = os.environ.copy()
    env["BOB_WEBHOOKS_FAIL_AFTER_BACKUP"] = "1"
    proc = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-File",
            str(REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"),
            "-SiteKit",
            "-PhysicalPath",
            str(site),
            "-WwwSource",
            str(www),
            "-Backend",
            "http://127.0.0.1:7700",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    assert proc.returncode != 0
    assert "rolled back site kit" in (proc.stdout + proc.stderr)
    assert marker.read_text(encoding="ascii") == "before"
    assert "SiteKit" in (REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1").read_text(encoding="ascii")
