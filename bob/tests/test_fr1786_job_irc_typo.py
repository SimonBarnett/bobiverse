"""FR #1786 / #1878: job-irc has no bbobiverse typo and no U+0008 before skill names."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IRC = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_fr1786_no_bbobiverse_or_backspace():
    for path in (IRC, LOG):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), path
        text = raw.decode("utf-8")
        assert "bbobiverse" not in text, path
        assert "\x08" not in text, path
        assert "bobiverse-bob-job-mrb" in text or path == LOG
        assert raw.endswith(b"\n"), path
