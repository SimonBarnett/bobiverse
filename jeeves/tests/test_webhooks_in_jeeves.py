from pathlib import Path
import re
import gh_filer
import bob_recycle

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def test_start_bobcallback_cmd_has_no_hardcoded_install_or_profile():
    t = (SCRIPTS / "Start-BobCallback.cmd").read_text(encoding="utf-8", errors="replace")
    assert "C:\\ai\\jeeves" not in t and "C:\\Python" not in t
    assert "set \"USERPROFILE=" not in t
    assert "%~dp0" in t and "bobcallback.py" in t and "--port 7700" in t


def test_gh_token_candidates_start_with_install_root_config():
    first = gh_filer._token_candidate_paths()[0]
    assert first == SCRIPTS.parent / "config" / "github.token"


def test_watch_webhooks_cooldown_param_name_matches_use():
    t = (SCRIPTS / "Watch-BobWebhooks.ps1").read_text(encoding="utf-8-sig")
    assert "$AnnounceCooldownMinutes" in t and "CooldownCooldown" not in t


def test_install_jeeves_registers_webhook_task_and_notes_optional_token():
    t = (SCRIPTS / "Install-Jeeves.ps1").read_text(encoding="utf-8-sig")
    assert "/TN BobCallback" in t and "Install-BobWebhooks.ps1" in t
    assert "report.secret" not in t and "github.token" in t  # token optional; no webhook secret


def test_recycle_prefers_installer_task_then_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(bob_recycle.os, "name", "nt")
    calls = []

    class R:
        returncode = 0

    monkeypatch.setattr(bob_recycle.subprocess, "run", lambda cmd, **k: (calls.append(cmd), R())[1])
    monkeypatch.setattr(bob_recycle, "_win_process_commandlines", lambda s: [])
    assert bob_recycle._restart_bobcallback_task() is True
    assert ["schtasks", "/Run", "/TN", "BobCallback"] in calls

    class Missing:
        returncode = 1

    monkeypatch.setattr(bob_recycle.subprocess, "run", lambda cmd, **k: Missing())
    assert bob_recycle._restart_bobcallback_task() is False
