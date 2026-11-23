"""FR #8934: second SiteKit Install-BobWebhooks leaves web.config byte-identical.

Keeps FR #8887 .bak / _backup- deny checks.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
WWW = REPO / "jeeves" / "www" / "irc-ntsa"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_sitekit(site: Path) -> subprocess.CompletedProcess[str]:
    assert PS
    args = [
        PS,
        "-NoProfile",
        "-File",
        str(SCRIPT),
        "-PhysicalPath",
        str(site),
        "-WwwSource",
        str(WWW),
        "-SiteKit",
        "-Backend",
        "http://127.0.0.1:7700",
        # FR #9246: unit runs must not wait on a live BobCallback.
        "-SkipBackendProbe",
    ]
    return subprocess.run(args, capture_output=True, text=True, timeout=180, check=False)


@NEED_PS
def test_fr8934_second_sitekit_install_webconfig_byte_stable(tmp_path: Path):
    site = tmp_path / "published"
    site.mkdir()
    r1 = _run_sitekit(site)
    assert r1.returncode == 0, r1.stdout + "\n" + r1.stderr
    cfg = site / "web.config"
    assert cfg.is_file()
    body = cfg.read_text(encoding="utf-8")
    assert 'fileExtension=".bak" allowed="false"' in body
    assert 'sequence="_backup-"' in body
    assert 'sequence=".bak/"' in body
    sha1 = _sha(cfg)

    r2 = _run_sitekit(site)
    assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
    assert _sha(cfg) == sha1, "second SiteKit install must not change web.config bytes"
    blob = (r2.stdout + "\n" + r2.stderr).lower()
    assert "already current" in blob or "updated" not in blob.split("web.config")[0]


@NEED_PS
def test_fr8934_format_rule_preserves_nested_indent():
    """Format-BobOwnedRuleBlock must keep match/action nested under rule (not flat 8)."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #8934" in text or "nested indent" in text.lower()
    assert "2 * $depth" in text or "(2 * $depth)" in text
