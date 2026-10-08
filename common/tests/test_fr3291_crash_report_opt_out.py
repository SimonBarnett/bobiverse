"""FR #3291: crash_report opt-out / local-only / no-log-tail."""
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


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    spool = tmp_path / "crash-spool"
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(spool))
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    monkeypatch.delenv("BOB_CRASH_REPORT_CONFIG", raising=False)
    monkeypatch.delenv("BOB_INTAKE_URL", raising=False)
    crash_report._installed_for = None
    crash_report._policy_cache = None
    yield spool


def _raise_once():
    try:
        raise RuntimeError("boom-fr3291")
    except RuntimeError as exc:
        return type(exc), exc, exc.__traceback__


def test_fr3291_env_off_spools_without_urlopen_or_gh(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_REPORT", "0")
    et, ev, tb = _raise_once()
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen, mock.patch(
        "crash_report._gh_search_open_sig"
    ) as gh_search, mock.patch("crash_report._gh_comment") as gh_comment:
        result = crash_report.report_exception("airc", et, ev, tb)
    assert result.get("ok") is True
    assert result.get("local_only") is True
    assert "spooled" in result
    assert Path(result["spooled"]).is_file()
    urlopen.assert_not_called()
    gh_search.assert_not_called()
    gh_comment.assert_not_called()


def test_fr3291_config_disabled_spools_without_network(tmp_path, monkeypatch):
    cfg = tmp_path / "crash-report.json"
    cfg.write_text(json.dumps({"enabled": False}), encoding="utf-8")
    monkeypatch.setenv("BOB_CRASH_REPORT_CONFIG", str(cfg))
    et, ev, tb = _raise_once()
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen, mock.patch(
        "crash_report._gh_search_open_sig", return_value=None
    ) as gh_search:
        result = crash_report.report_exception("airc", et, ev, tb)
    assert result.get("local_only") is True
    assert Path(result["spooled"]).is_file()
    urlopen.assert_not_called()
    gh_search.assert_not_called()


def test_fr3291_local_only_mode_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_REPORT", "local-only")
    et, ev, tb = _raise_once()
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen:
        result = crash_report.report_exception("bob-ear", et, ev, tb)
    assert result.get("local_only") is True
    urlopen.assert_not_called()


def test_fr3291_no_log_tail_omits_section(tmp_path, monkeypatch):
    cfg = tmp_path / "crash-report.json"
    cfg.write_text(
        json.dumps({"enabled": True, "mode": "full", "include_log_tail": False}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_CRASH_REPORT_CONFIG", str(cfg))
    log = tmp_path / "svc.log"
    log.write_text("secret line password=hunter2\n", encoding="utf-8")
    et, ev, tb = _raise_once()
    seen = {}

    def ok_post(title, body, *, repo, sig, exe):
        seen["body"] = body
        return {"ok": True}

    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda repo, sig: None)
    crash_report.report_exception(
        "airc", et, ev, tb, log_path=log, filer_post=ok_post
    )
    assert "### log tail" not in seen["body"]
    assert "hunter2" not in seen["body"]


def test_fr3291_disabled_empty_intake_url_does_not_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_REPORT", "0")
    monkeypatch.setenv("BOB_INTAKE_URL", "")
    et, ev, tb = _raise_once()
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen:
        result = crash_report.report_exception("airc", et, ev, tb)
    assert result.get("local_only") is True
    urlopen.assert_not_called()
    # Direct _post_intake must also refuse when disabled (no default URL send).
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen2:
        with pytest.raises(RuntimeError, match="crash-report disabled"):
            crash_report._post_intake("t", "b", repo="SimonBarnett/bobiverse", sig="abc", exe="airc")
    urlopen2.assert_not_called()


def test_fr3291_flush_spool_keeps_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_REPORT", "0")
    spool = Path(os.environ["BOB_CRASH_SPOOL"])
    spool.mkdir(parents=True, exist_ok=True)
    path = spool / "crash-abc.json"
    path.write_text(
        json.dumps(
            {
                "title": "crash: airc X",
                "body": "crash-sig:abc\n",
                "repo": "SimonBarnett/bobiverse",
                "sig": "abc",
                "exe": "airc",
            }
        ),
        encoding="utf-8",
    )
    with mock.patch("crash_report.urllib.request.urlopen") as urlopen:
        stats = crash_report.flush_spool()
    assert stats["sent"] == 0
    assert stats["kept"] >= 1
    assert path.is_file()
    urlopen.assert_not_called()


def test_fr3291_install_logs_off_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_CRASH_REPORT", "0")
    monkeypatch.setenv("BOB_CRASH_ALLOW_UNDER_PYTEST", "1")
    crash_report.install("unit-test-exe", flush=False)
    # logging may go to print/stderr via _log_policy
    # policy helper must report off
    p = crash_report.load_crash_report_policy()
    assert p.send is False
    assert "off" in p.log_label


def test_fr3291_airc_shell_off_default_disables(tmp_path, monkeypatch):
    root = tmp_path / "airc"
    (root / "config").mkdir(parents=True)
    (root / "config" / "airc.json").write_text(
        json.dumps({"shell": "off"}), encoding="utf-8"
    )
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(root))
    p = crash_report.load_crash_report_policy(install_root=root, product="airc")
    assert p.send is False
    assert p.source in {"airc-shell-off", "default-airc-no-agent", "config", "airc.json"}


def test_fr3291_msi_pack_and_install_source_gates():
    """Pack + Install-* must declare/forward BOBIVERSE_CRASH_REPORT (FR #3291)."""
    pack = (REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert 'Property Id="BOBIVERSE_CRASH_REPORT"' in pack
    assert '-CrashReport &quot;[BOBIVERSE_CRASH_REPORT]&quot;' in pack
    for rel in (
        "airc/scripts/Install-Airc.ps1",
        "bob/scripts/Install-Bob.ps1",
        "jeeves/scripts/Install-Jeeves.ps1",
    ):
        text = (REPO / rel).read_text(encoding="utf-8-sig")
        assert "[string]$CrashReport" in text, rel
        assert "crash-report.json" in text, rel
    airc_svc = (REPO / "airc" / "scripts" / "airc_console_service.py").read_text(
        encoding="utf-8"
    )
    assert "BOB_INSTALL_ROOT" in airc_svc
    assert "FR #3291" in airc_svc

