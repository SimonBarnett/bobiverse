"""FR #8695 / BOB-53: Priority MCP config host is mcp.ntsa.uk."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr8695_default_config_and_source_name_mcp_ntsa():
    cfg = json.loads((ROOT / "bob" / "tray" / "config" / "default.json").read_text(encoding="utf-8"))
    assert cfg["priorityMcpUrl"].startswith("https://mcp.ntsa.uk")
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    assert 'DefaultPriorityMcpUrl = "https://mcp.ntsa.uk/mcp"' in cs
    assert 'uri.Host, "mcp.ntsa.uk"' in cs
    # FR #9269: Configure MCP removed from Priority submenu; headless configure remains.
    assert "BeginConfigurePriorityMcp" in cs or "PriorityMcp.Configure" in cs
    assert 'MenuItems.Add("Configure MCP (mcp.ntsa.uk)")' not in cs
    assert 'MenuItems.Add("Start PriorityAgent")' not in cs
    assert "priority-catalog" in cs
    doc = (ROOT / "bob" / "docs" / "bob-53-priority-mcp-evidence.md").read_text(encoding="utf-8")
    assert "mcp.ntsa.uk" in doc
    assert "tray-lifecycle.log" in doc
