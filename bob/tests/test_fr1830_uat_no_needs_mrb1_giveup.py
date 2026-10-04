"""FR #1830: job-uat must not teach GIVEUP wait-for-needs-mrb1."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UAT = ROOT / "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_fr1830_uat_bans_needs_mrb1_giveup_gate():
    text = _utf8_no_bom(UAT)
    assert "1830" in text or "1717" in text
    assert "needs-human" in text
    assert "needs-mrb1" in text
    assert "CAST IRON" in text
    assert "wait for the label to be cleared" not in text
    assert "ACK then GIVEUP and wait" not in text


def test_fr1830_skill_harvest_log():
    text = _utf8_no_bom(LOG)
    assert "1830" in text
    assert "needs-mrb1" in text
