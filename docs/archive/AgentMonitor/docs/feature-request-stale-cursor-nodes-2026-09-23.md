<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-stale-cursor-nodes-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: stale cursor-agent nodes after `--new` / OOM TUI (issue #30)

https://github.com/SimonBarnett/AgentMonitor/issues/30

Simon paste 2026-09-23, flamingo, `windows=on`, kind=cursor, cwd=`E:\ai`. No UAT.

## LOCKED (watch log)

1. `--new` logged `prune stale cursor-agent pid=… (not session <new-guid>)` four times, then `cursor --new pruned 4 stale cursor-agent node(s)`.
2. The keep-id was a **brand-new** guid no live process had, so every `cursor-agent` node was treated as stale (including fleet `-p` `Git task` jobs and other TUIs whose command line has no session uuid).
3. `create-chat` failed; local session id only. Composer TUI spawn then logged `Composer node missing (OOM or bad session)` with `commitFreeGb` about 1–2 GB.
4. The loop logged `cursor Composer not running … - relaunch visible TUI`, called `create-chat` again, and spawned another TUI. Leftover nodes appeared (`mode=-p session~=?` and `mode=other`).
5. IRC forward `agent -p` without `--resume` has no session id on the command line, so `Test-CursorAgentForwardBusy` never matched and a second forward could stack.

## Gap vs `d2f237e`

`Stop-CursorAgentNodesExceptSession` killed any node that did not contain the new unused session id. Print-only helpers existed but the watch loop still relaunched the TUI after OOM.

## Acceptance

| ID | Gate |
|----|------|
| A1 | `--new` prunes only the previous watch session plus hung watch forwards / orphan `worker-server`. It does not Stop-Process a `Git task` / `long-running-background-tasks` node or another TUI that lacks that old session id. |
| A2 | After Composer node missing / OOM, the log does not say `relaunch visible TUI`. It switches to print-only and keeps IRC `agent -p` forwards. |
| A3 | `create-chat` runs at most once per `--new` until the next reset. |
| A4 | A live `forward-cursor.ps1` counts as busy even when the `-p` command line has no session uuid. |
| A5 | No UAT stamp. |

UNKNOWN: how much commit flamingo needs before a visible Composer TUI can stay up.
