"""FR #5642: updater pytest must not POST live FR #5279 intake.

MarchHare flooded intake with test shapes (0*64 sha256-mismatch) because
Apply paths call Set-Failure while temp InstallRoot has no crash-report.json
(fleet default allows intake) and Report-BobiverseIntakeIssue.ps1 resolves
from PSScriptRoot beside the real updater.

FR #5641 / PR #5643 already forwards -DryRun on Check. Apply still needs
BOB_CRASH_REPORT=local-only in the test env fixture.
"""
from __future__ import annotations

from repo_layout import ROOT

SELF = ROOT / "common/tests/test_service_self_update.py"
FALLBACK = ROOT / "common/tests/test_fr5353_release_lookup_fallback.py"
FOUR = ROOT / "common/tests/test_fr5354_four_part_release_asset.py"
LIST = ROOT / "common/tests/test_fr5412_list_msi_four_part.py"


def test_fr5642_service_self_update_env_sets_crash_report_local_only():
    t = SELF.read_text(encoding="utf-8")
    assert "FR #5642" in t
    assert "BOB_CRASH_REPORT" in t
    assert "local-only" in t
    i = t.index("def env(tmp_path)")
    chunk = t[i : i + 1400]
    assert 'e["BOB_CRASH_REPORT"] = "local-only"' in chunk
    assert "e.update(envvars or {})" in chunk


def test_fr5642_other_updater_env_fixtures_set_local_only():
    for path in (FALLBACK, FOUR, LIST):
        t = path.read_text(encoding="utf-8")
        assert 'e["BOB_CRASH_REPORT"] = "local-only"' in t, path.name
        assert "FR #5642" in t or "local-only" in t, path.name


def test_fr5876_airc_detached_apply_sets_local_only():
    t = (ROOT / "airc/tests/test_fr77_update_detached.py").read_text(encoding="utf-8")
    chunk = t[t.index("    # sha mismatch on Apply") : t.index("def test_loop_guard_and_pending_for_airc_product")]
    assert 'e["BOB_CRASH_REPORT"] = "local-only"' in chunk
    assert 'e["BOBIVERSE_CRASH_REPORT"] = "local-only"' in chunk
    assert "env=e" in chunk
    assert chunk.index('e["BOB_CRASH_REPORT"]') < chunk.index("p = subprocess.run(")
    assert 'assert result["lastResult"] == "sha256-mismatch"' in chunk
