"""MRB #2584 hostile: ComposeOnly reaches updater overlay; tip content gate; dual targets."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import REPO

COMMON = REPO / "common" / "scripts" / "Bobiverse-Common.ps1"
SYNC = REPO / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1"
DOC = REPO / "common" / "docs" / "post-install.md"


def _fn_body(text: str, name: str) -> str:
    m = re.search(r"function\s+" + re.escape(name) + r"\b", text)
    assert m, name
    rest = text[m.start() :]
    m2 = re.search(r"\nfunction\s+\w+", rest[1:])
    return rest if not m2 else rest[: m2.start() + 1]


def test_mrb2584_compose_only_still_reaches_updater_overlay():
    """ComposeOnly skips fetch/ff but must not exit before Sync-BobiverseUpdaterFromOrigin."""
    t = SYNC.read_text(encoding="utf-8")
    compose = t.find("if ($ComposeOnly)")
    call = t.find("Sync-BobiverseUpdaterFromOrigin")
    assert compose >= 0 and call > compose
    # No exit between robocopy scripts loop and overlay call
    robocopy = t.find("foreach ($d in @('scripts', 'third_party'))")
    between = t[robocopy:call]
    assert "exit " not in between.lower() or "exitcode" in between.lower()
    # DryRun exits before overlay; ComposeOnly must not
    dry = t.find("if ($DryRun)")
    assert dry >= 0 and dry < call


def test_mrb2584_overlay_writes_both_flat_and_common_targets():
    body = _fn_body(COMMON.read_text(encoding="utf-8"), "Sync-BobiverseUpdaterFromOrigin")
    assert "scripts\\Update-BobiverseService.ps1" in body or "scripts/Update-BobiverseService.ps1" in body
    assert "common\\scripts\\Update-BobiverseService.ps1" in body or "common/scripts/Update-BobiverseService.ps1" in body
    assert "FR #2563" in body
    assert "MaxAttempts" in body or "NoCount" in body


def test_mrb2584_post_install_docs_mention_overlay():
    text = DOC.read_text(encoding="utf-8")
    assert "FR #2581" in text
    assert "Sync-BobiverseUpdaterFromOrigin" in text
    assert "Update-BobiverseService.ps1" in text
