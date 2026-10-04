"""Hostile MRB #2283: DIGEST_ID_FOLD skill promote survives rebase keep-both."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))
import inbound_transcript as it  # noqa: E402

LOG = ROOT / "common/docs/skill-harvest-log.md"
DOC = ROOT / "bob/docs/bob-ear.md"
SKILL = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"


def test_mrb2283_fold_still_on_main_product():
    assert it.channel_list_for_machine("ionos") == "#bobiverse,#win-mpre8vi4u6u"


def test_mrb2283_docs_skill_log_keep_both_no_markers():
    for p in (LOG, DOC, SKILL):
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), p
        text = raw.decode("utf-8")
        assert "<<<<<<<" not in text
        assert "2280" in text or "DIGEST_ID_FOLD" in text
        assert "win-mpre8vi4u6u" in text
        assert "#ionos" not in it.channel_list_for_machine("ionos")
    # keep-both: parallel main lesson remains
    log = LOG.read_text(encoding="utf-8")
    assert "2274" in log or "keep-both" in log.lower() or "2237" in log
