# FR index: AgentIRC shared IRC host wrapper

**Digest:** https://github.com/SimonBarnett/bobiverse/issues/9972 (hold)  
**Vision:** `docs/feature-request-agentirc-2026-11-25.md`  
**Mocks:** `docs/mocks/agentirc/`  
**Consumers:** bobiverse#9793 (Depends-on #9972); SimonBarnett/jeeves-mcp#2 (Depends-on bobiverse#9972)

| code | issue | title | Depends-on (beyond digest) |
|---|---|---|---|
| digest | #9972 | Digest: AgentIRC (shared IRC host wrapper) | (none) |
| FR-A | #9973 | AgentIrc.dll package scaffold | digest |
| FR-B | #9974 | IRC JOIN-before-CLI + outbox API | #9973 |
| FR-C | #9975 | listen.txt `{nick}` → CLI stdin | #9974 |
| FR-D | #9976 | NotBusy edge + once-per-minute while idle | #9974 |
| FR-E | #9977 | bob-worker references AgentIrc.dll | #9975, #9976 |
| FR-F | #9978 | Jeeves/Priority reference AgentIrc.dll | #9975, #9976 |

## Related amendments (same turn)

| issue | change |
|---|---|
| #9793 | Depends-on #9972; IRC/inject via AgentIRC |
| #9796 | Depends-on #9972; outbox via AgentIRC API |
| #9797 | Depends-on #9972; stdin inject |
| #9807 | Rewritten: stdin only; no clipboard/copy-paste |
| jeeves-mcp#2 | Depends-on bobiverse#9972 |
| jeeves-mcp#9 | Depends-on bobiverse#9972 + #9978 |

Unhold **#9972** to release AgentIRC children.
