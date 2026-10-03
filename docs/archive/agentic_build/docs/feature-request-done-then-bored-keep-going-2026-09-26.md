<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-done-then-bored-keep-going-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: DONE then !bored — process MUST KEEP GOING

**Date:** 2026-09-26  
**Simon CAST IRON:** after every finished shop job, `!bored` must fire on
`#{machine}` so Jeeves assigns the next FR|MRB|UAT. The loop does not stop
after one DONE.

## Sequence

```text
ACK …
(work)
DONE … PASS|FAIL <url>
PRIVMSG #{machine} :!bored
(next assign → ACK → …)
```

## Who posts !bored

| Path | Who |
|------|-----|
| Preferred | `Watch-AgentHealth` / Sync-WatchBored within ~5s of DONE |
| Continuity | Seat appends `PRIVMSG #{machine} :!bored` same turn as DONE if monitor down/slow |

## Skills

- `bob-git-accept`
- `bob-mrb-worker`
- AgentMonitor `watch-seat` + seed `Get-GrokRules`
