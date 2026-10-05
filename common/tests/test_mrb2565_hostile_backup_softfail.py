"""Hostile MRB #2565 / FR #2563: catch-path ordering and docs gates after merge.

Additive tests (docs/mrb-2565): prove backup-fail does not burn MaxAttempts,
Ensure-ServiceRunning runs on pre-msi abort, and post-install documents ForceCheck.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

UPD = (ROOT / "common" / "scripts" / "Update-BobiverseService.ps1").read_text(encoding="utf-8-sig")
POST = (ROOT / "common" / "docs" / "post-install.md").read_text(encoding="utf-8-sig")


def test_apply_catch_backup_fail_uses_nocount_not_rolled_back_count():
    apply_ = UPD[UPD.index("function Invoke-Apply") :]
    catch = apply_[apply_.index("} catch {") :]
    assert "$isBackupFail" in catch
    assert "Set-Failure -Tag $tag -Result 'backup-failed' -NoCount" in catch
    # backup-fail branch must not share the counted rolled-back path
    assert re.search(
        r"if \(\$isBackupFail\) \{[^}]*backup-failed[^}]*NoCount[^}]*\} else \{[^}]*rolled-back",
        catch,
        re.S,
    )


def test_apply_catch_ensure_running_on_pre_msi_abort():
    apply_ = UPD[UPD.index("function Invoke-Apply") :]
    catch = apply_[apply_.index("} catch {") :]
    assert "Ensure-ServiceRunning -Why" in catch
    assert "backup-failed" in catch
    assert "apply-failed-pre-msi" in catch
    # Rollback still preferred when a tree backup exists
    assert "Invoke-Rollback" in catch


def test_backup_external_home_ge8_is_warn_not_throw():
    backup = UPD[UPD.index("function Backup-Install") : UPD.index("function Remove-OldBackups")]
    assert "backup-external-warn" in backup
    assert "continuing; tree backup ok" in backup or "continuing" in backup
    # Tree backup still throws on >=8 after retries
    assert "throw" in backup and "backup of install tree failed" in backup


def test_force_check_clears_failures_map_key():
    check = UPD[UPD.index("function Invoke-Check") :]
    assert "loop-guard-bypassed" in check
    assert "$st.failures.Remove($tag)" in check
    assert "ForceCheck" in check


def test_post_install_documents_backup_softfail_and_forcecheck():
    assert "## Self-update backup / loop-guard (FR #2563)" in POST
    assert "backup-failed" in POST
    assert "ForceCheck" in POST or "-ForceCheck" in POST
    assert "MaxAttempts" in POST
    assert ".pytest_cache" in POST or "peers.json" in POST


def test_fleet_ops_known_failure_row_for_fr2563():
    skill = (ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )
    assert "FR #2563" in skill
    assert "backup-failed" in skill or "robocopy" in skill.lower()
    assert "ForceCheck" in skill or "-ForceCheck" in skill
