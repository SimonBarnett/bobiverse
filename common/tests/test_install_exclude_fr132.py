"""FR #132: install .git/info/exclude must not silently skip new airc/jeeves paths."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON_PS1 = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
FR_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


@pytest.fixture(scope="module")
def common_ps1_text() -> str:
    assert COMMON_PS1.is_file(), COMMON_PS1
    return COMMON_PS1.read_text(encoding="utf-8")


def test_install_exclude_template_unignores_sibling_products(common_ps1_text: str):
    # Linked FR worktrees share this exclude; /* would otherwise hide new airc/tests files.
    assert "!/$Product/" in common_ps1_text or '!/$Product/' in common_ps1_text
    assert "!/common/" in common_ps1_text
    assert "!/airc/" in common_ps1_text
    assert "!/jeeves/" in common_ps1_text
    assert "git add -f" in common_ps1_text or "add -f" in common_ps1_text


def test_fr_skill_documents_force_add_for_sparse_exclude():
    assert FR_SKILL.is_file(), FR_SKILL
    text = FR_SKILL.read_text(encoding="utf-8")
    assert "git add -f" in text
    assert "exclude" in text.lower() or "sparse" in text.lower()
