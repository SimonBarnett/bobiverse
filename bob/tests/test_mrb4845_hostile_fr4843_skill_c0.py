"""docs/mrb-4845: FR #4843 skill bullets must stay contiguous without C0 controls."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _assert_clean_skill(rel: str, *needles: str) -> None:
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "\ufeff" not in text[:4]
    bad = [c for c in text if ord(c) < 32 and c not in "\n\r\t"]
    assert bad == [], f"C0 controls in {rel}: {[hex(ord(c)) for c in bad[:5]]}"
    for n in needles:
        assert n in text, f"missing {n!r} in {rel}"


def test_mrb4845_worker_skill_install_root_contiguous():
    _assert_clean_skill(
        ".grok/skills/bobiverse-bob-worker/SKILL.md",
        "Install-root job git (FR #4843)",
        "bob-wt-fr-<n>",
        "refuse_job_git",
        "install_root_branch_warning",
    )


def test_mrb4845_job_fr_skill_rebase_and_refuse_contiguous():
    _assert_clean_skill(
        ".grok/skills/bobiverse-bob-job-fr/SKILL.md",
        "never job-git the install root (FR #4843)",
        "merge / rebase",
        "refuse_job_git / install_root_branch_warning",
    )


def test_mrb4845_worker_seat_fr_star_contiguous():
    _assert_clean_skill(
        "agents/worker/.grok/skills/bobiverse-worker-seat/SKILL.md",
        "CAST IRON (FR #4843)",
        "left on fr-*",
    )
