"""MRB #3325 hostile: FR #3291 crash_report opt-out pins after product merge."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from repo_layout import REPO

SCRIPTS = REPO / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import crash_report  # noqa: E402


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    spool = tmp_path / "crash-spool"
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(spool))
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    monkeypatch.delenv("BOB_CRASH_REPORT_CONFIG", raising=False)
    monkeypatch.delenv("BOB_INTAKE_URL", raising=False)
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOB_PRODUCT", raising=False)
    crash_report._installed_for = None
    crash_report._policy_cache = None
    yield spool


def test_mrb3325_fleet_ops_and_airc_skills_pin_fr3291():
    fleet = _utf8_no_bom(REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md")
    assert "Opt-out (FR #3291)" in fleet or "FR #3291" in fleet
    idx = fleet.index("FR #3291")
    window = fleet[max(0, idx - 40) : idx + 420]
    assert "BOB_CRASH_REPORT" in window
    assert "crash-report.json" in window
    assert "BOBIVERSE_CRASH_REPORT" in window
    assert "shell=off" in window
    assert "spool" in window.lower()

    airc = _utf8_no_bom(REPO / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md")
    assert "Crash-report opt-out (FR #3291)" in airc
    aidx = airc.index("Crash-report opt-out (FR #3291)")
    aw = airc[aidx : aidx + 450]
    assert "enabled=false" in aw
    assert "BOBIVERSE_CRASH_REPORT" in aw
    assert "never POST" in aw or "never" in aw.lower()
    assert "crash-spool" in aw or "LOCALAPPDATA" in aw


def test_mrb3325_install_airc_preserve_and_shell_off_write():
    text = (REPO / "airc" / "scripts" / "Install-Airc.ps1").read_text(encoding="utf-8-sig")
    assert "[string]$CrashReport" in text
    assert "FR #3291" in text
    assert "keep prior" in text
    assert "airc-shell-off" in text
    assert "crash-report.json" in text
    # MSI off before prior-preserve before shell=off default.
    i_msi = text.index("$expCr -in @('0', 'false', 'no', 'off')")
    i_prior = text.index("keep prior")
    i_shell = text.index("$resolvedShell -eq 'off'")
    assert i_msi < i_prior < i_shell


def test_mrb3325_env_overrides_config_enabled(tmp_path, monkeypatch):
    cfg = tmp_path / "crash-report.json"
    cfg.write_text(json.dumps({"enabled": True, "mode": "full"}), encoding="utf-8")
    monkeypatch.setenv("BOB_CRASH_REPORT_CONFIG", str(cfg))
    monkeypatch.setenv("BOB_CRASH_REPORT", "0")
    p = crash_report.load_crash_report_policy()
    assert p.send is False
    assert p.source == "env"


def test_mrb3325_fleet_default_send_on_without_cues():
    p = crash_report.load_crash_report_policy(env={}, product="bob")
    assert p.send is True
    assert p.source == "default"


def test_mrb3325_disabled_skips_gh_search(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_REPORT", "local-only")

    def boom(*_a, **_k):
        raise AssertionError("gh must not run when local-only")

    try:
        raise RuntimeError("mrb3325-boom")
    except RuntimeError as exc:
        et, ev, tb = type(exc), exc, exc.__traceback__
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen, mock.patch(
        "crash_report._gh_search_open_sig", side_effect=boom
    ), mock.patch("crash_report._gh_comment", side_effect=boom):
        result = crash_report.report_exception("airc", et, ev, tb)
    assert result.get("local_only") is True
    urlopen.assert_not_called()
