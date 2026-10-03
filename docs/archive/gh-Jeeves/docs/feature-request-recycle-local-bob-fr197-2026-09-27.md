<!-- ARCHIVED COPY - source: SimonBarnett/gh-Jeeves @ 4ff29b5, path docs/feature-request-recycle-local-bob-fr197-2026-09-27.md, last changed 2026-09-27. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #197: !recycle documented by Jeeves, executed by local bob seat

## Split

- **Jeeves:** `!help` / `!help recycle`, auth, cooldown, shop wire `RECYCLE machine=…`.
- **Local bob seat / tray:** stop → owned orphan cleanup → git ff-only → reload skills → restart.

Jeeves never performs host-level process or Git operations for this command.

## Status

Implemented in-tree:

- Jeeves: registry + `recycle.py` + chair route
- Local executor: `tools/Invoke-BobSeatRecycle.ps1` (ordered steps, owned-process filter, git ff-only, tray restart)
