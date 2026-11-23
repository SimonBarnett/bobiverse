"""FR #7460: Install-BobWebhooks must not add a second <staticContent> (IIS 500)."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")

WWW = REPO / "jeeves" / "www" / "irc-ntsa"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _count_static(text: str) -> int:
    return text.lower().count("<staticcontent")


def _run_install(site: Path, www: Path) -> subprocess.CompletedProcess[str]:
    assert PS
    return subprocess.run(
        [
            PS,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-PhysicalPath",
            str(site),
            "-Backend",
            "http://127.0.0.1:7700",
            "-SkipBackendProbe",
            "-WwwSource",
            str(www),
            "-PublishWww",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _seed_www(tmp: Path) -> Path:
    www = tmp / "www-src"
    shutil.copytree(WWW, www)
    fav = REPO / "jeeves" / "www" / "favicon.ico"
    if fav.is_file():
        shutil.copy2(fav, www.parent / "favicon.ico")
    return www


@NEED_PS
@pytest.mark.parametrize(
    "fixture_name,body",
    [
        (
            "no_static",
            """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite><rules></rules></rewrite>
  </system.webServer>
</configuration>
""",
        ),
        (
            "other_mime",
            """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite><rules></rules></rewrite>
    <staticContent>
      <mimeMap fileExtension=".webp" mimeType="image/webp" />
    </staticContent>
  </system.webServer>
</configuration>
""",
        ),
        (
            "existing_ico",
            """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite><rules></rules></rewrite>
    <staticContent>
      <remove fileExtension=".ico" />
      <mimeMap fileExtension=".ico" mimeType="image/x-icon" />
    </staticContent>
  </system.webServer>
</configuration>
""",
        ),
    ],
)
def test_fr7460_install_keeps_single_staticcontent(tmp_path: Path, fixture_name: str, body: str):
    site = tmp_path / "iis"
    site.mkdir()
    cfg = site / "web.config"
    cfg.write_text(body, encoding="utf-8")
    www = _seed_www(tmp_path)

    r1 = _run_install(site, www)
    assert r1.returncode == 0, r1.stdout + "\n" + r1.stderr
    text1 = cfg.read_text(encoding="utf-8")
    assert _count_static(text1) == 1, f"{fixture_name}: expected one staticContent after first run"
    assert 'mimeType="image/x-icon"' in text1 or "mimeType='image/x-icon'" in text1
    assert text1.lower().count('fileextension=".ico"') >= 1
    # No duplicate mimeMap lines for .ico
    ico_maps = [
        ln
        for ln in text1.splitlines()
        if "mimemap" in ln.lower() and ".ico" in ln.lower()
    ]
    assert len(ico_maps) == 1, f"{fixture_name}: duplicate .ico mimeMap: {ico_maps}"

    sha1 = _sha(cfg)
    r2 = _run_install(site, www)
    assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
    text2 = cfg.read_text(encoding="utf-8")
    assert _count_static(text2) == 1
    assert _sha(cfg) == sha1, f"{fixture_name}: second run must leave web.config byte-identical"


@NEED_PS
def test_fr7460_collapses_preexisting_duplicate_staticcontent(tmp_path: Path):
    site = tmp_path / "iis"
    site.mkdir()
    cfg = site / "web.config"
    cfg.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite><rules></rules></rewrite>
    <staticContent>
      <mimeMap fileExtension=".webp" mimeType="image/webp" />
    </staticContent>
    <staticContent>
      <remove fileExtension=".ico" />
      <mimeMap fileExtension=".ico" mimeType="image/x-icon" />
    </staticContent>
  </system.webServer>
</configuration>
""",
        encoding="utf-8",
    )
    www = _seed_www(tmp_path)
    r = _run_install(site, www)
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    text = cfg.read_text(encoding="utf-8")
    assert _count_static(text) == 1
    assert "image/webp" in text
    assert "image/x-icon" in text


def test_fr7460_script_pins_merge_not_blind_append():
    text = SCRIPT.read_text(encoding="ascii")
    assert "7460" in text
    assert "staticContent" in text
    # Must not blindly append a fresh <staticContent> block on missing mimeType alone.
    assert "Merge-IcoStaticContent" in text or "Ensure-IcoStaticContent" in text or "FR #7460" in text