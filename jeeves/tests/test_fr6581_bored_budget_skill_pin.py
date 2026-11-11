"""FR #6581: jeeves skills must not claim stale-precompute budget-of-one."""
from __future__ import annotations

from pathlib import Path

import gitclaim

ROOT = Path(__file__).resolve().parents[1]
JEEVES_SKILL = ROOT / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"
TROUBLE_SKILL = ROOT / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    text = raw.decode("utf-8")
    assert raw.endswith(b"\n") or text.endswith("\n"), path
    return text


def test_fr6581_production_bored_budget_is_zero():
    assert gitclaim.BORED_GITHUB_CALL_BUDGET == 0
    src = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "BORED_GITHUB_CALL_BUDGET = 0" in src
    # Stale precompute uses the constant (not a hard-coded 1).
    assert "bored_budget = 0 if precompute_ok else BORED_GITHUB_CALL_BUDGET" in src
    assert "FR #3188 budget of 1" not in src


def test_fr6581_jeeves_skill_no_stale_budget_of_one():
    text = _utf8_no_bom(JEEVES_SKILL)
    assert "BORED_GITHUB_CALL_BUDGET = 0" in text or "BORED_GITHUB_CALL_BUDGET=0" in text
    assert "budget of 1 remains when precompute is stale" not in text
    assert "FR #3188 budget of 1" not in text
    assert "FR #3212" in text or "MRB #3207" in text
    # Offer-order bullet still documents zero-GitHub when fingerprint matches.
    assert "offer-precompute.json" in text
    assert "zero" in text.lower() and "GitHub" in text


def test_fr6581_troubleshooting_skill_no_budget_eq_one():
    text = _utf8_no_bom(TROUBLE_SKILL)
    assert "BORED_GITHUB_CALL_BUDGET=0" in text or "BORED_GITHUB_CALL_BUDGET = 0" in text
    assert "BORED_GITHUB_CALL_BUDGET=1" not in text
    assert "one** GitHub call budget" not in text
