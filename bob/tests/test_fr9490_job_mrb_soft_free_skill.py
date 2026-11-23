"""FR #9490: job-mrb skill documents soft free= (#9478), not busy-other-machine block."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MRB = ROOT / "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md"


def test_fr9490_skill_no_busy_other_machine_block():
    raw = MRB.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    # Stale FR #9401 wording must be gone.
    assert "even when that other seat is busy" not in text
    assert "(busy counts)" not in text
    # Soft free= semantics (FR #9478 / PR #9482) + #9480 carve-out stay in job-mrb.
    assert "free=free_seat_nicks" in text
    assert "FR #9478" in text
    assert "FR #9480" in text
    assert "9490" in text or "soft machine-id" in text
    # Do not park a second copy under harvest.
    harvest = ROOT / "common/.grok/skills/harvest/SKILL.md"
    if harvest.is_file():
        h = harvest.read_text(encoding="utf-8")
        assert "even when that other seat is busy" not in h or "9490" not in h
