<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-systray-agent-links-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: systray agent links not grey when apps installed (#180)

**Repos:** SimonBarnett/agentic_build. Tracking: SimonBarnett/agentic_irc#180.  
**Shape:** app (LOCKED)

## Ultimate objective

TipForm / Agents menu show Cursor and Grok in colour when the apps are installed on disk. Grey only when the exe is missing. Clicks launch Watch-AgentHealth (or install it) from Desktop or `C:\ai\AgentMonitor`.

## Shape

LOCKED

Primary: app

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Installed = exe | `Test-BobTrayAgentInstalled` true when Grok Bot.exe / Cursor.exe exists even if Desktop Watch-AgentHealth missing | offline assert | Still ANDs Watch-AgentHealth.cmd |
| S2 | Resolve paths | `Resolve-BobTrayAgentExe` finds Local\Programs\Grok Bot and Cursor variants | smoke | Hard-coded single path only |
| S3 | Monitor home | Watch-AgentHealth.cmd from Desktop **or** `C:\ai\AgentMonitor` | resolve helper | Only Desktop path |

## Gap

`Test-BobTrayAgentInstalled` required Desktop `Watch-AgentHealth.cmd` **and** exe — greys both apps when AgentMonitor is under `C:\ai\AgentMonitor` only.
