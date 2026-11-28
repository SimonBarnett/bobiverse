"""FR #9775: IRCD CI sparse-checkouts the Ergo payload and skips www."""
from __future__ import annotations

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-jeeves-ircd.yml"


def test_fr9775_ircd_workflow_sparse_and_no_www():
    text = WF.read_text(encoding="utf-8")
    assert "name: build-jeeves-ircd" in text
    assert "build-jeeves-ircd:" in text
    assert "sparse-checkout:" in text
    assert "Fetch-Ergo.ps1" in text
    assert "Install-BobIrcd.ps1" in text
    assert "name: jeeves-ircd" in text
    assert "ergo.exe" in text
    assert "default.yaml" in text
    assert "upload-artifact@v4" in text
    assert "jeeves/www" not in text
    assert "Copy-Item" not in text.split("www", 1)[0] or "jeeves\\www" not in text
    block = text.split("sparse-checkout:", 1)[1].split("sparse-checkout-cone-mode:", 1)[0]
    assert "jeeves/www" not in block
    assert "jeeves/**" not in block
