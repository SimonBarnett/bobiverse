"""docs/mrb-6110: FR #6108 docs no longer advertise VIA_EFORM/VIA_EXEC SDK opt-ins."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docs_mrb_6110_priority_client_winrun_only():
    """FR #7726 / #7130: interactive prepare form is WINRUN; Session 0 fail-closes."""
    text = (ROOT / "docs" / "airc-priority-client.md").read_text(encoding="utf-8")
    assert "Default `PRIORITY prepare form` still uses WINRUN on an interactive session" in text
    assert "in Session 0 it fail-closes `reason=session0_gui`" in text
    assert "PRIORITY prepare-form" in text


def test_docs_mrb_6110_remote_control_no_via_optin():
    text = (ROOT / "docs" / "airc-remote-control.md").read_text(encoding="utf-8")
    assert "FR #6108: no VIA_EFORM/VIA_EXEC SDK opt-in" in text


def test_docs_mrb_6110_priority_worker_readme():
    text = (ROOT / "priority-worker" / "README.md").read_text(encoding="utf-8")
    assert "console form prepare is WINRUN only (FR #6108)" in text
    assert "exactly one EFORM row" in text
