"""Hostile pins for MRB #3897 / FR #3894: OpenClipboard retry; never KEY_EVENT-drip long injects."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BW = ROOT / "bob" / "scripts" / "bob_worker.py"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def test_mrb3897_hostile_contiguous_open_clipboard_retry():
    text = BW.read_text(encoding="utf-8")
    assert "def _open_clipboard_retry(" in text
    assert "_KEY_FALLBACK_MAX_CHARS" in text
    assert "no KEY_EVENT drip" in text
    assert "relay: inject path=fail" in text or 'path=fail reason=clipboard' in text
    assert "relay: clipboard OpenClipboard failed" in text
    # Long paste-preferred lines must refuse KEY_EVENT fallback.
    assert "_inject_prefer_paste() and len(text) > int(_KEY_FALLBACK_MAX_CHARS)" in text


def test_mrb3897_hostile_skill_fr3894_bullet():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #2498 / #1601 / #3894" in skill or ("#3894" in skill and "OpenClipboard" in skill)
    assert "OpenClipboard" in skill
    assert "no KEY_EVENT" in skill or "per-char KEY_EVENT" in skill or "KEY_EVENTs" in skill
    assert "inject path=paste|keys|fail" in skill or "path=paste|keys|fail" in skill
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")


def test_mrb3897_hostile_constants_sane():
    import bob_worker as bw

    assert int(bw._KEY_FALLBACK_MAX_CHARS) <= 8
    assert int(getattr(bw, "_CLIPBOARD_OPEN_ATTEMPTS", 20)) >= 10
