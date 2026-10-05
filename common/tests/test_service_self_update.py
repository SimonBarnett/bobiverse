"""v0.1.17: service-start self-update (Update-BobiverseService.ps1) for ircBob / ircJeeves / Airc.

Behavioural tests run the real PowerShell updater against fake release JSON in a temp tree (Windows only);
static tests pin the safety properties (detached apply, no seat kill, no Ergo, no secrets, always exit 0).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

S = ROOT / "scripts"
UPD = S / "Update-BobiverseService.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")
REPO = "SimonBarnett/bobiverse"


def _t(name: str) -> str:
    return (S / name).read_text(encoding="utf-8-sig")


def _release(ver: str, product: str = "bob", sha: bool = True) -> dict:
    base = f"https://github.com/{REPO}/releases/download/v{ver}"
    assets = [{"name": f"{product}-{ver}.msi", "browser_download_url": f"{base}/{product}-{ver}.msi"}]
    if sha:
        assets.append({"name": f"{product}-{ver}.msi.sha256", "browser_download_url": f"{base}/{product}-{ver}.msi.sha256"})
    return {"tag_name": f"v{ver}", "assets": assets}


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "bob"
    root.mkdir()
    (root / "VERSION").write_text("0.1.16\n")
    state = tmp_path / "state"

    def run(*extra, release=None, mode="Check", envvars=None, product="bob", raw=None):
        args = [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(UPD), "-Product", product,
                "-InstallRoot", str(root), "-StateDir", str(state), "-Mode", mode]
        if release is not None:
            rj = tmp_path / "release.json"
            rj.write_text(raw if raw is not None else json.dumps(release))
            args += ["-ReleaseJson", str(rj)]
        args += list(extra)
        e = {k: v for k, v in os.environ.items() if k not in ("BOB_AUTOUPDATE", "BOBIVERSE_NO_UPDATE")}
        e.update(envvars or {})
        p = subprocess.run(args, capture_output=True, text=True, env=e, timeout=120)
        log = (state / "update.log").read_text() if (state / "update.log").exists() else ""
        return p, log

    run.root, run.state, run.tmp = root, state, tmp_path
    return run


@win
@pytest.mark.parametrize("var,val", [("BOB_AUTOUPDATE", "0"), ("BOB_AUTOUPDATE", "off"), ("BOBIVERSE_NO_UPDATE", "1")])
def test_optout_honoured(env, var, val):
    p, log = env(release=_release("0.1.17"), envvars={var: val})
    assert p.returncode == 0
    assert "skipped-optout" in log and "would-update" not in log


@win
def test_optout_marker_file(env):
    (env.root / "config").mkdir()
    (env.root / "config" / "autoupdate.disabled").write_text("")
    p, log = env(release=_release("0.1.17"))
    assert p.returncode == 0 and "skipped-optout" in log


@win
def test_newer_release_is_detected(env):
    p, log = env("-DryRun", release=_release("0.1.17"))
    assert p.returncode == 0
    assert "would-update local=0.1.16 latest=0.1.17" in log


@win
@pytest.mark.parametrize("latest", ["0.1.16", "0.1.15", "0.0.9"])
def test_same_or_older_is_noop_never_downgrades(env, latest):
    p, log = env("-DryRun", release=_release(latest))
    assert p.returncode == 0
    assert "result=current" in log and "would-update" not in log


@win
def test_offline_or_unreadable_release_starts_installed_version(env):
    p, log = env(release={}, raw="")                      # empty body
    assert p.returncode == 0 and ("starting installed version" in log or "no-release-data" in log)
    p, log = env(release={}, raw="{ not json")            # garbage
    assert p.returncode == 0
    assert "release-lookup-failed" in log
    # missing file == network failure stand-in
    args = [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(UPD), "-Product", "bob", "-InstallRoot",
            str(env.root), "-StateDir", str(env.state), "-ReleaseJson", str(env.tmp / "nope.json")]
    q = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert q.returncode == 0
    assert (env.root / "VERSION").read_text().strip() == "0.1.16"


@win
def test_release_without_sha256_asset_is_not_installed(env):
    p, log = env("-DryRun", release=_release("0.1.17", sha=False))
    assert p.returncode == 0 and "no-sha256-asset" in log and "would-update" not in log


@win
def test_foreign_asset_urls_are_rejected(env):
    rel = _release("0.1.17")
    for a in rel["assets"]:
        a["browser_download_url"] = "https://evil.example/x/" + a["name"]
    p, log = env("-DryRun", release=rel)
    assert p.returncode == 0 and "asset-url-rejected" in log and "would-update" not in log


@win
def test_other_products_asset_is_ignored(env):
    p, log = env("-DryRun", release=_release("0.1.17", product="jeeves"))
    assert p.returncode == 0 and "no-matching-asset" in log


@win
def test_loop_guard_blocks_a_failed_tag(env):
    env.state.mkdir()
    (env.state / "state.json").write_text(json.dumps({"failures": {"v0.1.17": 2}, "lastResult": "rolled-back",
                                                       "lastTag": "v0.1.17", "lastAttemptUtc": "2020-01-01T00:00:00Z"}))
    p, log = env("-DryRun", release=_release("0.1.17"))
    assert p.returncode == 0 and "blocked-loop-guard" in log and "would-update" not in log
    # a NEWER release is eligible again
    p, log = env("-DryRun", release=_release("0.1.18"))
    assert "would-update local=0.1.16 latest=0.1.18" in log


@win
def test_force_check_bypasses_loop_guard(env):
    """FR #2563: -ForceCheck clears MaxAttempts block so operators can escape a stuck tag."""
    env.state.mkdir()
    (env.state / "state.json").write_text(json.dumps({"failures": {"v0.1.17": 2}, "lastResult": "rolled-back",
                                                       "lastTag": "v0.1.17", "lastAttemptUtc": "2020-01-01T00:00:00Z"}))
    p, log = env("-DryRun", "-ForceCheck", release=_release("0.1.17"))
    assert p.returncode == 0, log
    assert "loop-guard-bypassed" in log, log
    assert "would-update local=0.1.16 latest=0.1.17" in log
    assert "blocked-loop-guard" not in log
    st = json.loads((env.state / "state.json").read_text(encoding="utf-8-sig"))
    assert "v0.1.17" not in (st.get("failures") or {})


@win
def test_backup_failed_result_does_not_block_next_check(env):
    """FR #2563: backup-only Apply failures use NoCount — failures stay 0 so next Check still schedules."""
    env.state.mkdir()
    (env.state / "state.json").write_text(json.dumps({
        "failures": {},
        "lastResult": "backup-failed",
        "lastTag": "v0.1.17",
        "lastAttemptUtc": "2020-01-01T00:00:00Z",
    }))
    p, log = env("-DryRun", release=_release("0.1.17"))
    assert p.returncode == 0, log
    assert "blocked-loop-guard" not in log
    assert "would-update local=0.1.16 latest=0.1.17" in log


@win
def test_pending_update_blocks_a_second_helper(env):
    from datetime import datetime, timezone
    env.state.mkdir()
    (env.state / "state.json").write_text(json.dumps({"pending": {"tag": "v0.1.17", "atUtc": datetime.now(timezone.utc).isoformat()}}))
    p, log = env("-DryRun", release=_release("0.1.17"))
    assert p.returncode == 0 and "skipped-pending" in log


@win
def test_pending_orphan_clears_when_helper_gone(env):
    """FR #1018: pending must not block 40 min when the helper task/process never started."""
    from datetime import datetime, timedelta, timezone
    env.state.mkdir()
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    (env.state / "state.json").write_text(json.dumps({
        "pending": {"tag": "v0.1.17", "atUtc": old},
        "lastResult": "scheduled",
        "lastTag": "v0.1.17",
    }))
    p, log = env("-DryRun", release=_release("0.1.17"))
    assert p.returncode == 0
    assert "pending-orphan" in log, log
    assert "skipped-pending" not in log
    st = json.loads((env.state / "state.json").read_text(encoding="utf-8-sig"))
    assert not st.get("pending")


def _plan(env, msi_bytes: bytes, sha_text: str):
    d = env.tmp / "assets"
    d.mkdir(exist_ok=True)
    msi = d / "bob-0.1.17.msi"
    msi.write_bytes(msi_bytes)
    sha = d / "bob-0.1.17.msi.sha256"
    sha.write_text(sha_text)
    env.state.mkdir(exist_ok=True)
    plan = env.state / "plan.json"
    plan.write_text(json.dumps({"product": "bob", "tag": "v0.1.17", "version": "0.1.17", "msiName": msi.name,
                                "msiUrl": str(msi), "shaUrl": str(sha)}))
    return plan


@win
def test_sha256_mismatch_aborts_and_records_failure(env):
    plan = _plan(env, b"not really an msi", "0" * 64 + "  bob-0.1.17.msi\n")
    p, log = env("-AllowLocalAssets", "-DelaySeconds", "0", "-PlanFile", str(plan), mode="Apply")
    assert p.returncode == 0
    assert "sha256-mismatch" in log and "service untouched" in log
    assert "msiexec" not in log and "service-stopped" not in log
    st = json.loads((env.state / "state.json").read_text(encoding="utf-8-sig"))
    assert st["failures"]["v0.1.17"] == 1
    assert (env.root / "VERSION").read_text().strip() == "0.1.16"


@win
def test_sha256_match_is_verified_and_verify_only_touches_nothing(env):
    data = b"pretend msi bytes"
    plan = _plan(env, data, hashlib.sha256(data).hexdigest() + "  bob-0.1.17.msi\n")
    p, log = env("-AllowLocalAssets", "-DelaySeconds", "0", "-VerifyOnly", "-PlanFile", str(plan), mode="Apply")
    assert p.returncode == 0
    assert "sha256-verified" in log and "verify-only done" in log
    assert "service-stopped" not in log and "backup-done" not in log
    assert (env.root / "VERSION").read_text().strip() == "0.1.16"


@win
def test_local_asset_urls_rejected_without_test_hook(env):
    data = b"x"
    plan = _plan(env, data, hashlib.sha256(data).hexdigest())
    p, log = env("-DelaySeconds", "0", "-PlanFile", str(plan), mode="Apply")
    assert p.returncode == 0 and "download-failed" in log


@win
def test_check_mode_exits_zero_for_bad_arguments(env):
    p, _ = env(product="nonsense", release=_release("0.1.17"))
    assert p.returncode == 0


# ----------------------------------------------------------------- static safety pins
def test_updater_apply_is_detached_never_inline_in_the_service():
    t = _t("Update-BobiverseService.ps1")
    assert "Register-ScheduledTask" in t and "Win32_Process" in t
    # the only msiexec invocation lives in Invoke-Apply (the detached helper), never in Invoke-Check
    check = t[t.index("function Invoke-Check"):t.index("# ---------------------------------------------------------------- main")]
    assert "msiexec" not in check.lower()
    assert "Start-DetachedApply" in check
    assert "/qn" in t and "/l*v" in t


def test_updater_backs_up_and_rolls_back():
    t = _t("Update-BobiverseService.ps1")
    apply_ = t[t.index("function Invoke-Apply"):]
    assert apply_.index("Backup-Install") < apply_.index("msiexec.exe")
    assert "Invoke-Rollback" in apply_
    assert "Install-" in t and "-NoStart" in t        # rollback re-registers the service from the restored tree


def test_fr2563_backup_excludes_volatile_retries_and_soft_fails():
    """FR #2563: volatile excludes, retry, disk-low warn, NoCount backup-fail, Ensure-ServiceRunning, ForceCheck escape."""
    t = _t("Update-BobiverseService.ps1")
    backup = t[t.index("function Backup-Install"):t.index("function Remove-OldBackups")]
    assert ".pytest_cache" in backup
    assert "peers.json" in backup
    assert "backup-retry" in backup
    assert "backup-warn disk-low" in backup
    assert "backup-robocopy-errors" in backup
    assert "NoCount" in t
    assert "backup-failed" in t
    assert "function Ensure-ServiceRunning" in t
    assert "loop-guard-bypassed" in t
    assert "-ForceCheck clears" in t or "ForceCheck clears" in t
    assert "backup of install tree failed" in t
    assert "Set-Failure -Tag $tag -Result 'backup-failed' -NoCount" in t or (
        "backup-failed" in t and "-NoCount" in t
    )
    assert "Ensure-ServiceRunning -Why" in t


def test_updater_never_kills_seats_or_touches_ergo_or_prints_secrets():
    t = _t("Update-BobiverseService.ps1")
    t = re.sub(r"<#.*?#>", "", t, flags=re.S)
    code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"Stop-Process|taskkill|\.Kill\(\)|Get-Process", code, re.I)
    assert not re.search(r"grok|cursor", code.replace(".grok\\skills", ""), re.I)   # only the skills folder is named
    # FR #2563: /XD dirs are built from an array that still includes ergo (never touch Ergo).
    code_no_xd = code.replace("'ergo'", "").replace('"ergo"', "")
    assert not re.search(r"ircd\.yaml|\\ergo\\|Join-Path[^\n]*'ergo'|BobIrcd", code_no_xd, re.I)
    assert not re.search(r"password|secret|token|oper\.cred", code.replace("-token", ""), re.I)
    assert re.search(r"\$xd\s*=\s*@\([^)]*'ergo'", t) or "'ergo'" in t[t.index("function Backup-Install"):t.index("function Remove-OldBackups")]
    assert "exit 0" in t


def test_updater_is_tokenless():
    t = _t("Update-BobiverseService.ps1")
    assert "Authorization" not in t and "GITHUB_TOKEN" not in t and "gh api" not in t


def test_updater_honours_both_opt_outs_and_logs():
    t = _t("Update-BobiverseService.ps1")
    assert "BOB_AUTOUPDATE" in t and "BOBIVERSE_NO_UPDATE" in t and "autoupdate.disabled" in t
    assert "update.log" in t and "state.json" in t


@pytest.mark.parametrize("wrapper,product,svc", [("Start-Bob.ps1", "bob", "ircBob"),
                                                 ("Start-Jeeves.ps1", "jeeves", "ircJeeves"),
                                                 ("Start-AircConsole.ps1", "airc", "Airc")])
def test_start_wrappers_run_the_updater_before_launch(wrapper, product, svc):
    t = _t(wrapper)
    assert "Update-BobiverseService.ps1" in t
    assert f"-Product {product}" in t and f"-ServiceName {svc}" in t
    assert "catch { Write-Host \"WARN self-update" in t        # a throwing updater can never block the start
    launch = {"Start-Bob.ps1": "irc_agent.py", "Start-Jeeves.ps1": "irc_agent.py", "Start-AircConsole.ps1": "airc_console_service.py"}[wrapper]
    # Compare executable body only: synopsis/comments may name the launch script before the updater call.
    body = re.sub(r"<#.*?#>", "", t, flags=re.S)
    body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    assert body.index("Update-BobiverseService.ps1") < body.index(launch)
    assert "Check-BobiverseUpdate.ps1" not in t               # the synchronous in-service msiexec path is gone


def test_install_jeeves_leaves_existing_ergo_alone():
    t = _t("Install-Jeeves.ps1")
    assert "[switch]$ForceErgo" in t
    guard = t.index("existing Ergo found")
    assert guard < t.index("Install-BobIrcd.ps1' )") if "Install-BobIrcd.ps1' )" in t else guard < t.index("$installBobIrcd = ")


def test_updater_state_dir_is_locked_down_and_lookups_throttled():
    t = _t("Update-BobiverseService.ps1")
    assert "icacls.exe $StateDir /inheritance:r" in t          # SYSTEM later runs a script copy + plan from here
    assert "throttled" in t                                       # crash-looping service must not hammer the API


def test_updater_restores_service_identity_after_msi():
    t = _t("Update-BobiverseService.ps1")
    assert "identity-reconcile" in t and "Invoke-ServiceReregister" in t
    assert "'-SkipErgo'" in t                                     # re-registering jeeves never re-runs Install-BobIrcd


def test_msi_installs_are_serialised_machine_wide():
    t = _t("Update-BobiverseService.ps1")
    assert "Global\\bobiverse-update-msi" in t
    assert t.index("Global\\bobiverse-update-msi") < t.index("stop-failed")
