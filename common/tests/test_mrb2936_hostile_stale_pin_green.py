"""Hostile pins for MRB #2936 / FR #2926 stale jeeves/common pin green-up.

Product already on main via #2936. Pins distinctive updated needles so a later
wipe cannot restore BOM-mandate / draft-True-only / ARP-heal flake gates.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

MSI = ROOT / "tests" / "test_msi_nssm_019.py"
FR611 = ROOT / "tests" / "test_fr611_intake_error_body.py"
WT = ROOT / "tests" / "test_worktree_sync_020.py"
GH = ROOT / "jeeves" / "tests" / "test_gh_filer.py"
MRB2583 = ROOT / "jeeves" / "tests" / "test_mrb2583_hostile_gh_filer_draft_pr.py"
SELF = ROOT / "jeeves" / "tests" / "test_jeeves_self_contained.py"
MRB2635 = ROOT / "jeeves" / "tests" / "test_mrb2635_hostile_jeeves_tests_green.py"
MRB1690 = ROOT / "tests" / "test_mrb1690_skill_consolidate_promote.py"
AGENT = ROOT / "tests" / "test_agent_layer_020.py"
AIROOT = ROOT / "tests" / "test_ai_root_020.py"
INTAKE = ROOT / "scripts" / "intake.py"


def _text(p: Path, *, require_trailing_nl: bool = True) -> str:
    t = p.read_text(encoding="utf-8")
    assert not t.startswith("\ufeff")
    # Some long-lived common pins ship without a final newline (ACCEPTABLE drift).
    if require_trailing_nl:
        assert t.endswith("\n")
    return t


def test_mrb2936_utf8_gate_not_bom_mandate():
    msi = _text(MSI)
    assert "FR #2301" in msi or "#2926" in msi
    assert "BOM optional" in msi or "valid UTF-8" in msi
    assert 'raw.decode("utf-8")' in msi or "raw.decode('utf-8')" in msi
    fr = _text(FR611)
    assert "BOM optional" in fr or "valid UTF-8" in fr


def test_mrb2936_worktree_arp_override_none():
    text = _text(WT)
    assert "ArpVersionOverride" in text
    assert '"none"' in text or "'none'" in text or " none" in text


def test_mrb2936_draft_bool_and_bob_worker_allowlist():
    assert "draft=True" in _text(GH)
    assert "_create_pr_with_files" in _text(MRB2583)
    assert "bool(draft)" in _text(MRB2583) or "bool(draft)" in _text(GH)
    assert "bob_worker.py" in _text(SELF)
    assert "test_mrb2482_pin_set_exact_six" in _text(MRB2635)


def test_mrb2936_skip_fr_allowlists_and_intake_ascii():
    m1690 = _text(MRB1690)
    assert 'assert "SKIP_FR" not in worker and "SKIP_FR" not in job' in m1690
    assert "nodejs.org" in _text(AGENT)
    assert "Clear-BobiverseJobWorktrees.ps1" in _text(AIROOT, require_trailing_nl=False)
    raw = INTAKE.read_bytes()
    assert b"\xe2\x80\xa6" not in raw
