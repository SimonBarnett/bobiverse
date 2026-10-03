<!-- ARCHIVED COPY - source: SimonBarnett/gh-Jeeves @ 4ff29b5, path docs/feature-request-recycle-machine-scope-fr211-2026-09-28.md, last changed 2026-09-28. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #211: !recycle {machine} vs bare all

## Behaviour
- `!recycle` / `!recycle all` → `RECYCLE machine=fleet scope=fleet` on #bobiverse (every bob-*)
- `!recycle {machinename}` → `RECYCLE machine=<id> scope=local` on command channel + #{machine}
- Unknown machine → denied with fleet list
- Aliases: dev1 → ce-priority-dev1

## Split
Jeeves routes only; bob-* announce restarting then execute (agentic_irc #249).