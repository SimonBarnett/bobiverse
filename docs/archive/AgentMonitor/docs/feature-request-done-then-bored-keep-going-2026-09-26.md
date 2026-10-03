<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-done-then-bored-keep-going-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: DONE then !bored — process MUST KEEP GOING

**Date:** 2026-09-26  
**Simon CAST IRON:** after every finished job, `!bored` must fire so Jeeves
assigns the next FR|MRB|UAT. The shop loop does not stop after one DONE.

## Wire

1. Bare `DONE …` (keyword first).
2. `PRIVMSG #{machine} :!bored` (monitor within ~5s of DONE, or seat same-turn if monitor lagging).
3. Next assign → ACK → work → DONE → `!bored` → …

## Code

- Monitor: `Sync-WatchBored` reason=`done` / `start` / idle (FR #100).
- Seat skill: `.grok/skills/watch-seat` CAST IRON section.
- Seed: `Get-GrokRules` in `Watch-AgentHealth.ps1`.

## Related

AgentMonitor issues #136 / #137 (IRC stay-up so !bored can drain).
