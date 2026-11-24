"""MRB #9573 hostile pin: jeeves-commands documents FR #9558 ACC-moved hold clear."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

DOC = REPO / "jeeves" / "docs" / "jeeves-commands.md"


def test_mrb9573_jeeves_commands_documents_fr9558_acc_moved_holds():
    text = DOC.read_text(encoding="utf-8")
    assert "FR #9558" in text
    assert "purge_orphan_seat_holds" in text
    assert "accept_offered" in text
    assert "ack-missing" in text
