# FR #8695 / BOB-53 evidence: Priority MCP is mcp.ntsa.uk

Success S1: Priority MCP configure records URL host mcp.ntsa.uk.

- **FR #9269:** Agents > Priority is a flat start (no Configure MCP submenu). Configure remains headless: `bob-tray.exe --priority-mcp-configure <snapshot.json>`.
- Default URL: `https://mcp.ntsa.uk/mcp` (`WorkerLauncher.DefaultPriorityMcpUrl` and `tray/config/default.json` `priorityMcpUrl`).
- A configured URL is accepted only when the scheme is https and the host is mcp.ntsa.uk. Any other host is rejected and the default is kept.
- Registration targets Grok user MCP `priority-catalog` at that URL, then writes `run/tray-priority-mcp.json` (`url`, `state`, `doctor`) and a `priority-mcp` line in `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log`.

Fail when the snapshot or log names a different host.
