# docs/mrb-4719: pin FR #4718 FAIL-queues-FIX skill text
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"

NEEDLE = (
    "FR #4718:** if DONE FAIL lands with no linked mrb-N-fix / fix(mrb-N) open, Jeeves queues one FIX for that head "
    "(resync does the same); the seat that FAILed is not offered that MRB again"
)


def test_fr4718_fail_queues_fix_contiguous_in_job_mrb():
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "exactly ONE separate fix PR" in text
