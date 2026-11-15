"""FR #7541: bob-tray-dialogs.md matches Format-BobCopilotPoolLine unlimited paint."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def test_fr7541_docs_unlimited_paints_unlimited_not_unknown():
    text = DOCS.read_text(encoding="utf-8-sig")
    assert "Unlimited Copilot without a historical max paints `unknown`" not in text
    assert "Unlimited Copilot without a historical max paints unknown" not in text
    assert "FR #7299" in text
    assert "Copilot - unlimited" in text or "`Copilot - unlimited`" in text
    assert "FR #7371" in text
    assert "overage_permitted" in text


def test_fr7541_format_still_returns_unlimited_word():
    src = HOVER.read_text(encoding="utf-8-sig")
    fmt = src[src.index("function Format-BobCopilotPoolLine") : src.index("function Get-BobCopilotMeterBarPct")]
    assert "return 'Copilot - unlimited'" in fmt or 'return "Copilot - unlimited"' in fmt
    assert "FR #7299" in fmt
    assert "FR #7371" in fmt or "overage_permitted" in fmt
