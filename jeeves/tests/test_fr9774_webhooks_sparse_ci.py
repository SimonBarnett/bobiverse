"""FR #9774: webhooks CI sparse-checkouts site-kit roots and keeps the artifact."""
from __future__ import annotations

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-jeeves-webhooks.yml"

_ROOTS = (
    "jeeves/www",
    "jeeves/assets",
    "jeeves/scripts/Install-BobWebhooks.ps1",
    "jeeves/scripts/jeeves_webhooks_ci.py",
    "bob/tray/assets/ntsa-gut-logo.png",
    "bob/tray/assets/bob-systray.ico",
    "common/scripts",
)


def test_fr9774_webhooks_workflow_sparse_checkout():
    text = WF.read_text(encoding="utf-8")
    assert "name: build-jeeves-webhooks" in text
    assert "build-jeeves-webhooks:" in text
    assert "sparse-checkout:" in text
    assert "sparse-checkout-cone-mode: false" in text
    assert "name: jeeves-webhooks" in text
    assert "MANIFEST.json" in text
    assert "upload-artifact@v4" in text
    for root in _ROOTS:
        assert root in text
    block = text.split("sparse-checkout:", 1)[1].split("sparse-checkout-cone-mode:", 1)[0]
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    assert "jeeves/**" not in lines
    assert "jeeves" not in lines
    assert "jeeves/www" in lines
