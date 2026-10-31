"""FR #5277: UPDATE Apply/Check always leave the product service Running."""
from __future__ import annotations

from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
MATRIX = ROOT / "airc/docs/airc-update-restart-matrix.md"
VISION = ROOT / "airc/docs/feature-request-airc-remote-update-restart-2026-10-31.md"


def test_fr5277_apply_finally_heals_service():
    t = UPD.read_text(encoding="utf-8-sig")
    fn = t[t.index("function Invoke-Apply") : t.index("function Invoke-Check")]
    fin = fn[fn.rindex("} finally {") :]
    assert "Ensure-ServiceRunning" in fin
    assert "apply-finally-heal" in fin or "FR #5277" in fin
    assert "msiexec-timeout" in fn
    assert "download-failed" in fn
    assert "function Ensure-ServiceRunning" in t


def test_fr5277_matrix_covers_failure_classes():
    raw = MATRIX.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    m = raw.decode("utf-8")
    assert "\u2014" not in m
    assert "120s" in m or "120 s" in m
    for cls in (
        "download-failed",
        "stop-failed",
        "backup-failed",
        "msiexec-exit",
        "msiexec-timeout",
        "apply-skip",
        "current",
        "rollback",
    ):
        assert cls in m
    assert "Ensure-ServiceRunning" in m
    assert "inline msiexec" in m.lower() or "never inline" in m.lower()
    vis = VISION.read_text(encoding="utf-8")
    assert "5277" in vis
    assert "password=" not in m.lower()


def test_fr5277_console_still_detached_no_inline_msiexec():
    con = (ROOT / "airc/scripts/airc_console.py").read_text(encoding="utf-8")
    sched = con[con.index("def schedule_fleet_update") : con.index("def schedule_fleet_update") + 2500]
    assert "msiexec" not in sched.lower() or "never" in sched.lower()
    assert "Update-BobiverseService" in con
