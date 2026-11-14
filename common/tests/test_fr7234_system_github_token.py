"""FR #7234: SYSTEM ear gets a GitHub token source; miss lists checked sources.

Si: service as SYSTEM must fetch Copilot itself. missing_token on MarchHare means
no GH_TOKEN / config\\github.token / gh_filer path. Want: Install/Start-Bob
provisions config\\github.token (SYSTEM+Administrators ACL) from operator
sign-in; on miss, digest/ear log name which sources were checked (never values).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import bobreport
import copilot_dispatch as cd
from repo_layout import ROOT

COMMON_PS1 = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL_BOB = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
START_BOB = ROOT / "bob" / "scripts" / "Start-Bob.ps1"


def _system_env(monkeypatch, tmp_path: Path, *, install: Path) -> None:
    sys_home = tmp_path / "systemprofile"
    sys_home.mkdir(exist_ok=True)
    monkeypatch.setenv("USERPROFILE", str(sys_home))
    monkeypatch.setenv("LOCALAPPDATA", str(sys_home / "AppData" / "Local"))
    (sys_home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("SystemDrive", str(tmp_path))
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(install / "home"))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("BOB_COPILOT_OBSERVE", raising=False)
    monkeypatch.delenv("BOB_CONFIG_DIR", raising=False)
    monkeypatch.setattr(bobreport, "_is_local_system_process", lambda: True)
    monkeypatch.setattr(bobreport.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        bobreport.sys,
        "executable",
        str(install / "scripts" / "bob-ear.exe"),
        raising=False,
    )
    (install / "scripts").mkdir(parents=True, exist_ok=True)
    (install / "scripts" / "bob-ear.exe").write_bytes(b"MZ")
    (install / "config").mkdir(parents=True, exist_ok=True)
    (install / "home").mkdir(parents=True, exist_ok=True)


def test_fr7234_missing_token_lists_checked_sources_under_localsystem(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    # Isolate gh_filer so live operator tokens cannot satisfy the miss path.
    monkeypatch.setattr(
        bobreport,
        "resolve_github_token_for_ear",
        bobreport.resolve_github_token_for_ear,
    )

    def _no_gh_filer():
        raise RuntimeError("gh_filer_blocked")

    import sys

    class _Blocked:
        @staticmethod
        def ensure_gh_token_env():
            raise RuntimeError("gh_filer_blocked")

    monkeypatch.setitem(sys.modules, "gh_filer", _Blocked)

    tok, src = bobreport.resolve_github_token_for_ear()
    assert tok == ""
    assert src == "none"
    resolve = bobreport.last_github_token_resolve()
    checked = resolve.get("checked") or []
    assert "env:GH_TOKEN" in checked
    assert "env:GITHUB_TOKEN" in checked
    assert "file:install/config/github.token" in checked
    assert "gh_filer" in checked
    # Names only — never a token-shaped value.
    blob = " ".join(str(x) for x in checked)
    assert "FAKE_" not in blob
    assert not re.search(r"ghp_[A-Za-z0-9]+", blob)
    assert not re.search(r"github_pat_[A-Za-z0-9_]+", blob)

    pool = bobreport.fetch_live_copilot_pool(install / "home", now=50.0)
    assert pool.get("state") == "unknown"
    acq = bobreport.last_copilot_acquisition()
    assert acq.get("kind") == "missing_token"
    assert acq.get("error") == "no_token"
    acq_checked = acq.get("checked_sources") or []
    assert "env:GH_TOKEN" in acq_checked
    assert "file:install/config/github.token" in acq_checked
    line = bobreport.format_fuel_publish_diag(
        {
            "copilot_acquisition": "missing_token",
            "copilot_source": "none",
            "copilot_checked": ",".join(acq_checked),
        }
    )
    assert "copilot_acquisition=missing_token" in line
    assert "copilot_checked=" in line
    assert "env:GH_TOKEN" in line
    assert "FAKE_" not in line


def test_fr7234_install_token_still_resolves_and_hides_value(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    secret = "FAKE_GH_TOKEN_7234_SECRET"
    (install / "config" / "github.token").write_text(secret, encoding="utf-8")
    tok, src = bobreport.resolve_github_token_for_ear()
    assert tok == secret
    assert src == "file:github.token"
    assert secret not in src
    resolve = bobreport.last_github_token_resolve()
    assert resolve.get("source") == "file:github.token"
    assert secret not in str(resolve)


def test_fr7234_publish_diag_carries_checked_on_missing(
    monkeypatch, tmp_path: Path
):
    install = tmp_path / "bob"
    _system_env(monkeypatch, tmp_path, install=install)
    import sys

    class _Blocked:
        @staticmethod
        def ensure_gh_token_env():
            raise RuntimeError("gh_filer_blocked")

    monkeypatch.setitem(sys.modules, "gh_filer", _Blocked)
    home = install / "home"
    mid = "marchhare"
    import bobstat

    bobstat.write_peer(
        home,
        {
            "id": mid,
            "ok": True,
            "online": True,
            "status": "operational",
            "weekly": 1,
            "weekly_known": True,
        },
    )
    monkeypatch.setattr(bobreport, "post_report_json", lambda payload, url=None: 204)
    monkeypatch.setattr(
        bobreport,
        "resolve_fuel_report_target",
        lambda url=None, env=None: {
            "ok": True,
            "url": "https://bob.ntsa.uk/bob/v1/report",
            "host": "bob.ntsa.uk",
            "path": "/bob/v1/report",
            "source": "test",
            "error": None,
        },
    )
    monkeypatch.setattr(bobreport, "fetch_live_xai_weekly", lambda: None)
    monkeypatch.setattr(
        bobreport,
        "enrich_peer_keep_last_good_xai_weekly",
        lambda peer, error=None: dict(peer),
    )
    monkeypatch.setattr(
        bobreport, "read_local_opencode_fuel_doc", lambda force=False: {}
    )
    monkeypatch.setattr(bobreport, "read_grok_account_label", lambda: ("none", None))
    monkeypatch.setattr(bobstat, "refresh_peer_cursor_remaining", lambda *a, **k: None)

    code = bobreport.publish_local_peer_fuel(home, mid, force=True, now=1_700_000_000.0)
    assert code == 204
    diag = bobreport.last_fuel_publish_diag()
    assert diag.get("copilot_acquisition") in ("missing_token", "unread")
    checked = diag.get("copilot_checked") or ""
    assert "env:GH_TOKEN" in checked
    assert "file:install/config/github.token" in checked
    line = bobreport.format_fuel_publish_diag(diag)
    assert "copilot_checked=" in line
    assert "FAKE_" not in line
    assert "ghp_" not in line


def test_fr7234_ensure_helper_and_hooks_exist():
    text = COMMON_PS1.read_text(encoding="utf-8-sig")
    assert "function Ensure-BobiverseGithubToken" in text
    assert "FR #7234" in text
    assert "Get-BobiverseInteractiveUserHome" in text
    assert "Protect-BobiverseSecretPath" in text
    assert "gh auth token" in text
    # Never echo the token variable.
    assert "Write-Host $token" not in text
    assert "Write-Output $token" not in text
    install = INSTALL_BOB.read_text(encoding="utf-8-sig")
    assert "Ensure-BobiverseGithubToken" in install
    start = START_BOB.read_text(encoding="utf-8-sig")
    assert "Ensure-BobiverseGithubToken" in start


def test_fr7234_ensure_provisions_from_env_token(tmp_path: Path):
    """Live PS: Ensure writes config\\github.token from env and ACL-locks it."""
    install = tmp_path / "bob"
    (install / "config").mkdir(parents=True)
    fake = "FAKE_GH_TOKEN_7234_ENV_PROVISION"
    # Dot-source Common and call Ensure with GH_TOKEN set; never print value.
    ps = f"""
$ErrorActionPreference = 'Stop'
. '{COMMON_PS1}'
$env:GH_TOKEN = '{fake}'
$env:GITHUB_TOKEN = ''
$r = Ensure-BobiverseGithubToken -InstallRoot '{install}'
if (-not $r.Ok) {{ throw 'Ensure failed' }}
if ($r.Source -ne 'env:GH_TOKEN') {{ throw ('bad source=' + $r.Source) }}
$dest = Join-Path '{install}' 'config\\github.token'
$got = (Get-Content -LiteralPath $dest -Raw).Trim()
if ($got -ne $env:GH_TOKEN) {{ throw 'token mismatch' }}
Write-Output ('ok source=' + $r.Source + ' len=' + $got.Length)
"""
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok source=env:GH_TOKEN" in proc.stdout
    assert fake not in proc.stdout
    written = (install / "config" / "github.token").read_text(encoding="utf-8").strip()
    assert written == fake
