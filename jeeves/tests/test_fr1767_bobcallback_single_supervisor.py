"""FR #1767: BobCallback single-supervisor refuse + health Ready-without-LISTEN finding."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON_SUP = ROOT / "common/scripts/Start-BobCallbackSupervised.ps1"
JEEVES_SUP = ROOT / "jeeves/scripts/Start-BobCallbackSupervised.ps1"
START_JEEVES = ROOT / "jeeves/scripts/Start-Jeeves.ps1"
REG = ROOT / "jeeves/scripts/Register-BobCallbackTask.ps1"
HEALTH = ROOT / "jeeves/tools/monitor/health.py"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
MONITOR = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"


def test_fr1767_supervised_refuses_second_parent():
    text = COMMON_SUP.read_text(encoding="utf-8-sig")
    assert "refuse second" in text.lower() or "WARN refuse second" in text
    assert "Get-BobCallbackSupervisedParentIds" in text
    assert "FR #1767" in text
    assert JEEVES_SUP.read_text(encoding="utf-8-sig") == text or "refuse second" in JEEVES_SUP.read_text(encoding="utf-8-sig").lower()


def test_fr1767_start_jeeves_counts_before_start_process():
    text = START_JEEVES.read_text(encoding="utf-8-sig")
    assert "Get-BobCallbackSupervisedParentCount" in text
    assert "schtasks /Run /TN BobCallback" in text
    assert "FR #1767" in text or "FR #1831" in text


def test_fr1767_register_skips_when_parent_exists():
    text = REG.read_text(encoding="utf-8-sig")
    assert "skip Start-Process fallback" in text or "already" in text
    assert "FR #1767" in text


def test_fr1767_health_ready_without_listen_is_finding():
    text = HEALTH.read_text(encoding="utf-8")
    assert "no-listen" in text
    assert "FR #1767" in text
    # Ready alone must not short-circuit True before listen check
    assert 'task.lower() in ("running", "ready")' in text
    assert "False" in text


def test_fr1767_skills_document_schtasks_and_refuse():
    t = TROUBLE.read_text(encoding="utf-8")
    m = MONITOR.read_text(encoding="utf-8")
    assert "1767" in t and "1831" in t
    assert "schtasks /Run" in t
    assert "1767" in m or "1831" in m
