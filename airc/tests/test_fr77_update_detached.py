"""FR #77: airc UPDATE schedules the detached updater; never inline msiexec; identity preserved."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from repo_layout import ROOT

import airc_console as ac

S = ROOT / "scripts"
UPD = S / "Update-BobiverseService.ps1"
START = S / "Start-AircConsole.ps1"
INSTALL = S / "Install-Airc.ps1"
INSTALL_CONSOLE = S / "Install-AircConsole.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")


def _core(auth_ops=("bob-marchhare",), machine="marchhare", **kw):
    auth = ac.AuthPolicy(operators=set(auth_ops), machine=machine)
    return ac.AircConsoleCore(machine=machine, auth=auth, nick=f"{machine}_console", **kw)


def test_parse_update_command_shapes():
    assert ac.parse_update_command("UPDATE airc") == ("airc", None)
    assert ac.parse_update_command("UPDATE airc 0.1.20") == ("airc", "0.1.20")
    assert ac.parse_update_command("UPDATE airc v0.1.20") == ("airc", "0.1.20")
    assert ac.parse_update_command("UPDATE bob 1.2.3") == ("bob", "1.2.3")
    assert ac.parse_update_command("UPDATE jeeves") == ("jeeves", None)
    assert ac.parse_update_command("update airc") == ("airc", None)  # case-insensitive verb
    assert ac.parse_update_command("UPDATE evil") is None
    assert ac.parse_update_command("UPDATE airc 1.2") is None
    assert ac.parse_update_command("whoami") is None
    assert ac.parse_update_command("UPDATE airc now") is None


def test_update_authorized_schedules_detached_never_msiexec_inline():
    calls = []

    def scheduler(product, version=None, **kwargs):
        calls.append({"product": product, "version": version, **kwargs})
        return ac.UpdateScheduleResult(
            ok=True,
            status="scheduled",
            detail="via=scheduled-task local=0.1.19 latest=0.1.20",
            product=product,
            version=version or "0.1.20",
        )

    core = _core(update_scheduler=scheduler)
    r = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE airc 0.1.20")
    assert r is not None
    assert r.action == "update"
    assert r.reply and r.reply.startswith("UPDATE accepted")
    assert "product=airc" in r.reply
    assert "0.1.20" in r.reply
    assert calls and calls[0]["product"] == "airc" and calls[0]["version"] == "0.1.20"
    # reply lands before any transport stop: scheduler returns without msiexec
    assert all("msiexec" not in str(c).lower() for c in calls)


def test_update_denied_for_unauthorized_nick():
    core = _core(auth_ops=("bob-marchhare",))
    r = core.handle_raw(":evil!e@h PRIVMSG marchhare_console :UPDATE airc")
    assert r and r.action == "deny"


def test_update_rejects_non_allowlisted_product_token():
    core = _core()
    # parse gate: unknown product never reaches scheduler
    r = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE notepad")
    assert r and r.action == "pipe"  # falls through to shell (not a fleet UPDATE)


def test_update_duplicate_pending_suppressed():
    def scheduler(product, version=None, **kwargs):
        return ac.UpdateScheduleResult(
            ok=False,
            status="skipped-pending",
            detail="tag=v0.1.20",
            product=product,
            version=version,
        )

    core = _core(update_scheduler=scheduler)
    r = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :UPDATE airc")
    assert r and r.action == "update"
    assert "skipped-pending" in (r.reply or "")


def test_update_help_mentions_verb():
    core = _core()
    r = core.handle_raw(":bob-marchhare!u@h PRIVMSG marchhare_console :.help")
    assert r and r.action == "help"
    assert "UPDATE" in (r.reply or "")


def test_schedule_fleet_update_invokes_check_mode_not_msiexec(tmp_path, monkeypatch):
    """Real helper must call Update-BobiverseService Check (detached), never msiexec in-process."""
    upd = tmp_path / "Update-BobiverseService.ps1"
    # stub: record argv; never mention msiexec success path for Check
    upd.write_text(
        "param($Product,$Mode,$InstallRoot,$ServiceName,$TargetVersion,$ForceCheck,$NoSpawn)\n"
        "Write-Output \"STUB product=$Product mode=$Mode tv=$TargetVersion force=$ForceCheck\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.19\n")
    recorded = []

    real_run = subprocess.run

    def fake_run(args, **kwargs):
        recorded.append(list(args))
        return real_run(args, **kwargs)

    monkeypatch.setattr(ac.subprocess, "run", fake_run)
    res = ac.schedule_fleet_update(
        "airc",
        version="0.1.20",
        install_root=str(root),
        updater_script=str(upd),
    )
    assert res.ok or res.status in {"scheduled", "scheduled-nospawn", "current", "skipped-pending", "spawn-failed", "check-ran"}
    assert recorded, "powershell updater must be invoked"
    cmd = " ".join(recorded[0]).lower()
    assert "update-bobiverseservice.ps1" in cmd
    assert "-mode" in cmd and "check" in cmd
    assert "msiexec" not in cmd
    assert "-targetversion" in cmd and "0.1.20" in " ".join(recorded[0])


def test_machine_id_canonical_order_and_explicit_hostname(monkeypatch):
    monkeypatch.delenv("AIRC_CONSOLE_MACHINE", raising=False)
    monkeypatch.delenv("BOB_MACHINE_ID", raising=False)
    monkeypatch.setenv("COMPUTERNAME", "WIN-MPRE8VI4U6U")

    mid, src = ac.resolve_machine_id("Ionos")
    assert mid == "ionos" and src == "arg"

    monkeypatch.setenv("AIRC_CONSOLE_MACHINE", "flamingo")
    mid, src = ac.resolve_machine_id(None)
    assert mid == "flamingo" and src == "AIRC_CONSOLE_MACHINE"

    monkeypatch.delenv("AIRC_CONSOLE_MACHINE", raising=False)
    monkeypatch.setenv("BOB_MACHINE_ID", "marchhare")
    mid, src = ac.resolve_machine_id(None)
    assert mid == "marchhare" and src == "BOB_MACHINE_ID"

    monkeypatch.delenv("BOB_MACHINE_ID", raising=False)
    mid, src = ac.resolve_machine_id(None, allow_hostname_fallback=True)
    assert mid == "win-mpre8vi4u6u" and src == "COMPUTERNAME"

    with pytest.raises(ac.MachineIdUnresolved):
        ac.resolve_machine_id(None, allow_hostname_fallback=False)


def test_updater_script_check_has_no_msiexec_and_airc_identity_hooks():
    t = UPD.read_text(encoding="utf-8-sig")
    check = t[t.index("function Invoke-Check") : t.index("# ---------------------------------------------------------------- main")]
    assert "msiexec" not in check.lower()
    assert "Start-DetachedApply" in check
    assert "TargetVersion" in t or "-TargetVersion" in t
    # identity + no Ergo
    assert "ConsoleHome" in t and "MachineId" in t
    assert "identity-reconcile" in t
    assert "/XD ergo" in t
    assert "'-SkipErgo'" in t or "-SkipErgo" in t


def test_start_airc_runs_updater_before_python_and_warns_hostname():
    t = START.read_text(encoding="utf-8-sig")
    assert "Update-BobiverseService.ps1" in t
    assert t.index("Update-BobiverseService.ps1") < t.index("airc_console_service.py")
    assert "msiexec" not in t.lower()
    assert "Write-Warning" in t and "COMPUTERNAME" in t
    assert "AIRC_CONSOLE_MACHINE" in t and "BOB_MACHINE_ID" in t


def test_install_airc_preserves_consolehome_machineid_nostart():
    for path in (INSTALL, INSTALL_CONSOLE):
        t = path.read_text(encoding="utf-8-sig")
        assert "[string]$MachineId" in t or "$MachineId" in t
        assert "ConsoleHome" in t
        assert "[switch]$NoStart" in t


def test_updater_airc_reregister_passes_machineid_consolehome():
    t = UPD.read_text(encoding="utf-8-sig")
    # airc branch of Invoke-ServiceReregister
    assert "'airc'" in t or '"airc"' in t
    idx = t.index("function Invoke-ServiceReregister")
    block = t[idx : idx + 2500]
    assert "ConsoleHome" in block and "MachineId" in block


def test_external_homes_include_airc_console_password_store():
    """Rollback/backup must cover .airc / .airc-console where console.password lives."""
    t = UPD.read_text(encoding="utf-8-sig")
    assert ".airc-console" in t and ".airc" in t
    # updater must not read console.password / ergo.password (homes are copied opaquely)
    code = re.sub(r"<#.*?#>", "", t, flags=re.S)
    code = "\n".join(l for l in code.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"console\.password|ergo\.password|nickserv", code, re.I)


def test_service_reconnect_budget_within_120s():
    svc = (ROOT / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "IDLE_DEAD_S = 120" in svc or "IDLE_DEAD_S=120" in svc.replace(" ", "")
    assert "RECONNECT_MIN_S" in svc and "RECONNECT_MAX_S" in svc
    # SASL + console.password reuse
    assert "console.password" in svc
    assert "ensure_nickserv_password" in svc


def test_docs_and_skill_document_update_verb():
    remote = (ROOT / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "UPDATE airc" in remote
    skill = (ROOT / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md").read_text(encoding="utf-8")
    assert "UPDATE" in skill


@win
def test_fake_release_target_version_allowlist_and_hash(tmp_path):
    """TargetVersion path: allowlisted asset OK; foreign URL rejected; sha mismatch aborts."""
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n")
    state = tmp_path / "state"
    state.mkdir()

    def run_check(release: dict, extra=None):
        rj = tmp_path / "release.json"
        rj.write_text(json.dumps(release), encoding="utf-8")
        args = [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            "airc",
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            "Check",
            "-DryRun",
            "-ForceCheck",
            "-TargetVersion",
            "0.1.17",
            "-ReleaseJson",
            str(rj),
        ]
        if extra:
            args += extra
        p = subprocess.run(args, capture_output=True, text=True, timeout=120)
        log = (state / "update.log").read_text(encoding="utf-8") if (state / "update.log").exists() else ""
        return p, log

    base = "https://github.com/SimonBarnett/bobiverse/releases/download/v0.1.17"
    good = {
        "tag_name": "v0.1.17",
        "assets": [
            {"name": "airc-0.1.17.msi", "browser_download_url": f"{base}/airc-0.1.17.msi"},
            {"name": "airc-0.1.17.msi.sha256", "browser_download_url": f"{base}/airc-0.1.17.msi.sha256"},
        ],
    }
    p, log = run_check(good)
    assert p.returncode == 0
    assert "would-update" in log or "result=would-update" in log

    bad = json.loads(json.dumps(good))
    for a in bad["assets"]:
        a["browser_download_url"] = "https://evil.example/" + a["name"]
    p, log = run_check(bad)
    assert p.returncode == 0
    assert "asset-url-rejected" in log

    # sha mismatch on Apply
    d = tmp_path / "assets"
    d.mkdir(exist_ok=True)
    msi = d / "airc-0.1.17.msi"
    msi.write_bytes(b"not-an-msi")
    sha = d / "airc-0.1.17.msi.sha256"
    sha.write_text("0" * 64 + "  airc-0.1.17.msi\n")
    plan = state / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "product": "airc",
                "tag": "v0.1.17",
                "version": "0.1.17",
                "msiName": msi.name,
                "msiUrl": str(msi),
                "shaUrl": str(sha),
            }
        ),
        encoding="utf-8",
    )
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            "airc",
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            "Apply",
            "-AllowLocalAssets",
            "-DelaySeconds",
            "0",
            "-PlanFile",
            str(plan),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    log = (state / "update.log").read_text(encoding="utf-8")
    assert p.returncode == 0
    assert "sha256-mismatch" in log and "service untouched" in log
    assert "msiexec" not in log


@win
def test_loop_guard_and_pending_for_airc_product(tmp_path):
    root = tmp_path / "airc"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n")
    state = tmp_path / "state"
    state.mkdir()
    (state / "state.json").write_text(
        json.dumps({"failures": {"v0.1.17": 2}, "lastResult": "rolled-back", "lastTag": "v0.1.17", "lastAttemptUtc": "2020-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    rel = {
        "tag_name": "v0.1.17",
        "assets": [
            {
                "name": "airc-0.1.17.msi",
                "browser_download_url": "https://github.com/SimonBarnett/bobiverse/releases/download/v0.1.17/airc-0.1.17.msi",
            },
            {
                "name": "airc-0.1.17.msi.sha256",
                "browser_download_url": "https://github.com/SimonBarnett/bobiverse/releases/download/v0.1.17/airc-0.1.17.msi.sha256",
            },
        ],
    }
    rj = tmp_path / "r.json"
    rj.write_text(json.dumps(rel), encoding="utf-8")
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            "airc",
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            "Check",
            "-DryRun",
            "-ForceCheck",
            "-ReleaseJson",
            str(rj),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    log = (state / "update.log").read_text(encoding="utf-8")
    # FR #2563: -ForceCheck clears MaxAttempts (operator escape); without it, blocked-loop-guard.
    assert p.returncode == 0, log
    assert "loop-guard-bypassed" in log, log
    assert "would-update" in log
    assert "blocked-loop-guard" not in log

    from datetime import datetime, timezone

    (state / "state.json").write_text(
        json.dumps({"pending": {"tag": "v0.1.17", "atUtc": datetime.now(timezone.utc).isoformat()}}),
        encoding="utf-8",
    )
    p = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(UPD),
            "-Product",
            "airc",
            "-InstallRoot",
            str(root),
            "-StateDir",
            str(state),
            "-Mode",
            "Check",
            "-DryRun",
            "-ForceCheck",
            "-ReleaseJson",
            str(rj),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    log = (state / "update.log").read_text(encoding="utf-8")
    assert p.returncode == 0 and "skipped-pending" in log


def test_service_wires_update_action_reply():
    svc = (ROOT / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert '"update"' in svc or "'update'" in svc
    # must reply before any stop; update action sends privmsg
    assert "hr.action" in svc
