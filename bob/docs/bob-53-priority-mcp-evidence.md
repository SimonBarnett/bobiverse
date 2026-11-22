# FR #8695 / BOB-53 evidence: Priority MCP is mcp.ntsa.uk

Success S1: Agents > Priority configures MCP so the recorded URL host is mcp.ntsa.uk.

- Compiled tray: Agents > Priority > Configure MCP (mcp.ntsa.uk).
- Default URL: `https://mcp.ntsa.uk/mcp` (`WorkerLauncher.DefaultPriorityMcpUrl` and `tray/config/default.json` `priorityMcpUrl`).
- A configured URL is accepted only when the scheme is https and the host is mcp.ntsa.uk. Any other host is rejected and the default is kept.
- The click registers Grok user MCP `priority-catalog` at that URL, then writes `run/tray-priority-mcp.json` (`url`, `state`, `doctor`) and a `priority-mcp` line in `%LOCALAPPDATA%\Bobiverse\tray-lifecycle.log`.
- Headless: `bob-tray.exe --priority-mcp-configure <snapshot.json>`.

Fail when the snapshot or log names a different host.
