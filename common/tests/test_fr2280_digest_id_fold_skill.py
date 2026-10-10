"""Harvest #2280: DIGEST_ID_FOLD playbook in docs/skills + channel_list fold."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "common" / "scripts"))
import inbound_transcript as it  # noqa: E402

LOG = ROOT / "common/docs/skill-harvest-log.md"
DOC = ROOT / "bob/docs/bob-ear.md"
SKILL = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"


def test_fr2280_channel_list_folds_ionos_alias():
    assert it.channel_list_for_machine("ionos") == "#bobiverse,#wonderland,#win-mpre8vi4u6u"
    assert it.channel_list_for_machine("win-mpre8vi4u6u") == "#bobiverse,#wonderland,#win-mpre8vi4u6u"
    assert "#ionos" not in it.channel_list_for_machine("ionos")


def test_fr2280_docs_and_harvest_log():
    for p in (LOG, DOC, SKILL):
        text = p.read_text(encoding="utf-8")
        assert "2280" in text or "DIGEST_ID_FOLD" in text
        assert "win-mpre8vi4u6u" in text
        assert not p.read_bytes().startswith(b"\xef\xbb\xbf")
        assert p.read_bytes().endswith(b"\n")
