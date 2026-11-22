# BOB-47 Agents > Plan MCP

Agents > Plan writes `run/plan-mcp.json` with the plan server URL `https://plan.ntsa.uk/mcp`.

The tray log line is `plan-mcp url=https://plan.ntsa.uk/mcp`. That is the config `grok mcp doctor` is measured against. A missing or different URL fails this slice.
