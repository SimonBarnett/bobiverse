<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/dumb-service-fr236.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #236: DUMB service version (design scaffold)

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/236

## Goal
Always-on DUMB presence as a real service (Windows SCM / systemd), persistent
TLS to Ergo, account-bound operators (consume FR #230 CAP account map),
DPAPI-sealed PSK, LocalSystem/root identity, interactive PM shell for verified
accounts. Protocol stays DUMB v1 (Python reference).

## Phases
1. **Scaffold (this PR):** design doc, skill update, offline tests that encode
   acceptance gates (service unit presence, account filter wiring, empty
   operators refuse).
2. **Windows service host:** SCM install/uninstall, restart backoff, LocalSystem.
3. **Linux systemd unit:** root unit, restart=on-failure.
4. **Account-bound exec + PM shell:** integrate `accounts.json` / CAP tags from
   #230; audit log; spoof drop.
5. **DPAPI key path + exec hard-config:** no optional jail flags for service mode.

## Non-goals
Not a git-task worker. No `#bobiverse` announce. No Form Prep / MRB / UAT.
Default nick `m3-<hostname>`. Pair on private channel only.

## Related
- `.grok/skills/agentic-dumb/SKILL.md`
- `docs/mode3-dumb-ops.md`
- Issues #230, #231
