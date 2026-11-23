"""FR #8887: publish backups stay outside the web root; requestFiltering denies .bak / _backup-."""
from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
STAMP = REPO / "jeeves" / "scripts" / "Stamp-PriorityAgentDownloads.ps1"
WWW = REPO / "jeeves" / "www" / "irc-ntsa"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")

BACKUP_NAME_RE = re.compile(r"(^|[/\\])_backup-", re.IGNORECASE)
BAK_NAME_RE = re.compile(r"\.bak$", re.IGNORECASE)
# Heuristic scan: line mentions a backup write token AND a web-root token.
BACKUP_TOKEN_RE = re.compile(
    r"(?i)(\.bak\b|_backup-|site-kit-bak|fr\d+\.[^\s'\"]*\.bak)"
)
WEBROOT_TOKEN_RE = re.compile(
    r"(?i)(PhysicalPath|inetpub|irc-ntsa|WwwSource|webConfig\b|jeeves/www)"
)
OK_MARKER_RE = re.compile(r"backup-path-ok:\s*\S+")

WS_RULE = """        <rule name="WsircWebSocket7999" stopProcessing="true">
          <match url="^wsirc(/.*)?$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:8097/wsirc{R:1}" />
        </rule>
"""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _run(site: Path, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
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
        # FR #9246: unit runs must not wait on a live BobCallback.
        "-SkipBackendProbe",
        *extra,
    ]
    return subprocess.run(
        args, capture_output=True, text=True, timeout=180, check=False, env=env
    )


def _seed_cfg(with_ws: bool = False) -> str:
    rules = WS_RULE if with_ws else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
{rules}        <rule name="BobReportWebhook" stopProcessing="true">
          <match url="^bob/v1/report$" ignoreCase="true" />
          <action type="Rewrite" url="http://127.0.0.1:7700/bob/v1/report" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"""


def _assert_no_backup_names(root: Path) -> None:
    bad: list[str] = []
    for p in root.rglob("*"):
        name = p.name
        if BAK_NAME_RE.search(name) or BACKUP_NAME_RE.search(str(p.relative_to(root))):
            bad.append(str(p.relative_to(root)))
    assert not bad, f"backup-shaped names under web root: {bad}"


def _assert_filtering(cfg_text: str) -> None:
    root = ET.fromstring(cfg_text)
    bak = [
        el
        for el in root.iter()
        if _local(el.tag) == "add"
        and el.attrib.get("fileExtension") == ".bak"
        and el.attrib.get("allowed", "").lower() == "false"
    ]
    assert len(bak) == 1, cfg_text
    seqs = {
        el.attrib.get("sequence")
        for el in root.iter()
        if _local(el.tag) == "add" and "sequence" in el.attrib
    }
    assert "_backup-" in seqs and ".bak/" in seqs, seqs
    assert len([el for el in root.iter() if _local(el.tag) == "requestFiltering"]) == 1


@NEED_PS
def test_fr8887_default_backup_outside_web_root(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    (site / "web.config").write_text(_seed_cfg(), encoding="utf-8")
    www = tmp_path / "www-src"
    shutil.copytree(WWW, www)

    r1 = _run(site, "-WwwSource", str(www), "-PublishWww")
    assert r1.returncode == 0, r1.stdout + "\n" + r1.stderr
    _assert_no_backup_names(site)
    bak_dir = tmp_path / "_backup-www-irc-ntsa"
    assert (bak_dir / "web.config").is_file()
    assert (bak_dir / "site").is_dir()

    r2 = _run(site, "-WwwSource", str(www), "-PublishWww")
    assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
    _assert_no_backup_names(site)
    assert (bak_dir / "web.config").is_file()


@NEED_PS
def test_fr8887_explicit_backup_root_and_inroot_rejected(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    (site / "web.config").write_text(_seed_cfg(), encoding="utf-8")
    off = tmp_path / "off-root"
    off.mkdir()

    r = _run(site, "-BackupRoot", str(off))
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    _assert_no_backup_names(site)
    assert (off / "_backup-www-irc-ntsa" / "web.config").is_file()

    bad = _run(site, "-BackupRoot", str(site))
    assert bad.returncode != 0
    assert "FR #8887" in (bad.stdout + bad.stderr)
    _assert_no_backup_names(site)


@NEED_PS
def test_fr8887_site_kit_rollback_uses_offroot_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    (site / "web.config").write_text(_seed_cfg(), encoding="utf-8")
    (site / "keep.txt").write_text("alive\n", encoding="utf-8")
    www = tmp_path / "www-src"
    shutil.copytree(WWW, www)
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["BOB_WEBHOOKS_FAIL_AFTER_BACKUP"] = "1"
    r = _run(site, "-WwwSource", str(www), "-SiteKit", env=env)
    assert r.returncode != 0
    assert "rolled back site kit" in (r.stdout + r.stderr).lower()
    assert (site / "keep.txt").read_text(encoding="utf-8") == "alive\n"
    _assert_no_backup_names(site)


@NEED_PS
@pytest.mark.parametrize(
    "seed",
    [
        "minimal",
        "with_security",
        "with_rf_selfclose",
        "with_fe_expanded",
        "with_bak_allowed_true",
        "with_ws",
    ],
)
def test_fr8887_request_filtering_shapes(tmp_path: Path, seed: str):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    if seed == "minimal":
        body = _seed_cfg()
    elif seed == "with_ws":
        body = _seed_cfg(with_ws=True)
    elif seed == "with_security":
        body = _seed_cfg().replace(
            "</system.webServer>",
            """    <security>
      <requestFiltering allowDoubleEscaping="true">
        <fileExtensions allowUnlisted="true">
          <add fileExtension=".ico" allowed="true" />
        </fileExtensions>
        <hiddenSegments><clear /></hiddenSegments>
      </requestFiltering>
    </security>
  </system.webServer>""",
        )
    elif seed == "with_rf_selfclose":
        body = _seed_cfg().replace(
            "</system.webServer>",
            """    <security>
      <requestFiltering allowDoubleEscaping="true" />
    </security>
  </system.webServer>""",
        )
    elif seed == "with_fe_expanded":
        body = _seed_cfg().replace(
            "</system.webServer>",
            """    <security>
      <requestFiltering allowDoubleEscaping="true">
        <fileExtensions allowUnlisted="true">
          <add fileExtension=".ico" allowed="true" />
          <add fileExtension=".png" allowed="true" />
        </fileExtensions>
        <hiddenSegments><clear /></hiddenSegments>
      </requestFiltering>
    </security>
  </system.webServer>""",
        )
    else:  # with_bak_allowed_true
        body = _seed_cfg().replace(
            "</system.webServer>",
            """    <security>
      <requestFiltering allowDoubleEscaping="true">
        <fileExtensions allowUnlisted="true">
          <add fileExtension=".bak" allowed="true" />
        </fileExtensions>
        <hiddenSegments><clear /></hiddenSegments>
      </requestFiltering>
    </security>
  </system.webServer>""",
        )
    cfg = site / "web.config"
    cfg.write_text(body, encoding="utf-8")

    def _ws(cfg_text: str) -> str | None:
        m = re.search(r'(?s)<rule name="WsircWebSocket7999".*?</rule>', cfg_text)
        return m.group(0) if m else None

    before_ws = _ws(body)

    r1 = _run(site)
    assert r1.returncode == 0, r1.stdout + "\n" + r1.stderr
    text1 = cfg.read_text(encoding="utf-8")
    _assert_filtering(text1)
    _assert_no_backup_names(site)
    if before_ws is not None:
        assert _ws(text1) == before_ws, "websocket rules must stay byte-identical"

    r2 = _run(site)
    assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
    text2 = cfg.read_text(encoding="utf-8")
    assert text2 == text1, "second run must be byte-identical"
    if before_ws is not None:
        assert _ws(text2) == before_ws


def test_fr8887_stamper_makes_no_backup(tmp_path: Path):
    if not STAMP.is_file():
        pytest.skip("stamper missing")
    html = tmp_path / "index.html"
    html.write_text(
        '<a href="PriorityAgent.exe">Priority Agent</a>\n', encoding="utf-8"
    )
    if not PS:
        pytest.skip("powershell required")
    r = subprocess.run(
        [PS, "-NoProfile", "-File", str(STAMP), "-HtmlPath", str(html)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    # Stamper may warn when no release fixture; it must not create backups.
    _assert_no_backup_names(tmp_path)
    assert not list(tmp_path.glob("*.bak"))


def test_fr8887_script_scan_no_inroot_backup_writes():
    roots = [
        REPO / "jeeves" / "scripts",
        REPO / ".github" / "workflows",
    ]
    exts = {".ps1", ".py", ".yml", ".yaml"}
    hits: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in exts:
                continue
            if "tests" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith(("#", "//", "<!--")):
                    continue
                if BACKUP_TOKEN_RE.search(line) and WEBROOT_TOKEN_RE.search(line):
                    if OK_MARKER_RE.search(line):
                        continue
                    # Off-root destination patterns are fine.
                    if "_backup-www-" in line or "BackupRoot" in line or "configBak" in line:
                        continue
                    if "must not be inside" in line or "never inside" in line.lower():
                        continue
                    hits.append(f"{path.relative_to(REPO)}:{i}:{line.strip()}")
    assert not hits, "scripts write backup next to web-root tokens:\n" + "\n".join(hits)


def test_fr8887_tracked_www_has_no_backup_artefacts():
    bad: list[str] = []
    for path in WWW.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(WWW)).replace("\\", "/")
        if BAK_NAME_RE.search(path.name) or BACKUP_NAME_RE.search(rel):
            bad.append(rel)
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"_backup-" in raw.lower() or b".bak" in path.name.encode("ascii", "ignore"):
            # Content mention of the deny sequences in docs HTML is ok; names only.
            pass
    assert not bad, bad


def test_fr8887_installer_ascii_bomless():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw.decode("ascii")
    text = raw.decode("ascii")
    assert "BackupRoot" in text
    assert "Ensure-BackupRequestFiltering" in text
    assert "fr8803.$stamp.bak" not in text
    assert "$webConfig.fr" not in text or "configBak" in text
