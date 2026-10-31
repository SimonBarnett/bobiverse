"""Hostile MRB #5326: python UPDATE intake redacts secret-shaped detail."""
from __future__ import annotations

import airc_console as ac


def test_mrb5326_python_intake_redacts_detail():
    # Assemble hunter-shaped text at runtime (FR #3304).
    secret = "FAKE" + "_" + "EXAMPLE99"
    raw = "password=" + secret + " token=" + secret
    out = ac.report_update_failure_intake(
        product="airc",
        result="spawn-failed",
        tag="v1.0.0",
        detail=raw,
        dry_run=True,
    )
    blob = (out.get("title") or "") + "\n" + (out.get("body") or "")
    assert secret not in blob
    assert "password=" in blob or "redacted" in blob.lower()
    assert out.get("kind") == "issue"
    assert "airc-update-fail" in (out.get("idempotency_key") or "")
