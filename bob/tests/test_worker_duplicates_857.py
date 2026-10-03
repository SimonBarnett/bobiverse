"""t857u: the worker skills/docs make a PR author find and close duplicate FRs/issues of what the PR fixes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / ".grok" / "skills"


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def test_fr_skill_requires_duplicate_search_comment_close_and_pr_body_list():
    s = _t(SK / "bobiverse-bob-job-fr" / "SKILL.md")
    assert "(t857u)" in s and "Duplicate of #N / fixed by PR #M" in s
    assert "--reason \"not planned\"" in s and "Duplicates closed:" in s
    assert "Closes <owner>/<repo>#D" in s
    assert s.index("Duplicates: find and close them") < s.index("Evidence required")


def test_mrb_skill_verifies_and_closes_missed_duplicates():
    s = _t(SK / "bobiverse-bob-job-mrb" / "SKILL.md")
    assert "(t857u)" in s and "Duplicate of #N / fixed by PR #M" in s
    assert "Duplicates closed:" in s and "not planned" in s and "needs-human" in s


def test_done_wire_skill_and_worker_doc_carry_the_rule():
    irc = _t(SK / "bobiverse-bob-job-irc" / "SKILL.md")
    assert "Duplicates first (t857u)" in irc and "Duplicates closed:" in irc
    doc = _t(ROOT / "docs" / "bob-worker.md")
    assert "Duplicates (t857u)" in doc and "Duplicate of #N / fixed by PR #M" in doc