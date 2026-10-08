"""docs/mrb-3470: hostile pins for FR #3400 orphan ACK release skill text."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

COMMANDS = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-commands/SKILL.md"
TROUBLE = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"
PRODUCT_TEST = ROOT / "jeeves/tests/test_fr3400_orphan_accepted_release.py"


def test_mrb3470_commands_assign_documents_orphan_release_and_absent_refuse():
    t = COMMANDS.read_text(encoding="utf-8")
    assert "FR #3400" in t
    assert "prior ACK void" in t
    assert "not in the shop channel" in t
    assert "Never steal from a live accepted holder" in t
    # Contiguous !assign cell still mentions departed-nick release.
    assert "accepted only under a departed nick" in t


def test_mrb3470_troubleshooting_documents_worker_remove_release():
    t = TROUBLE.read_text(encoding="utf-8")
    assert "FR #3400" in t
    assert "release_accepted_for_departed_nick" in t
    assert "prior ACK void" in t
    assert "worker-remove" in t


def test_mrb3470_product_tests_still_present():
    assert PRODUCT_TEST.is_file()
    t = PRODUCT_TEST.read_text(encoding="utf-8")
    assert "release_accepted_for_departed_nick" in t
    assert "test_assign_refuses_absent_nick" in t
    assert "test_worker_remove_releases_accepted" in t
