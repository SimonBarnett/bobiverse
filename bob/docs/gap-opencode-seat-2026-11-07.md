# Gap analysis --- OpenCode as bobiverse seat (vs origin/main 88a5ec9e)

Compared Success rows to modules on detached `origin/main` worktree `repo/` and live install `C:\ai\bob` (2026-11-07).

| Success / gap | origin/main state | Live install | Gap |
|---------------|-------------------|--------------|-----|
| Seat kind + fuel math | #6120/#6121 merged | bob-worker.exe ASCII has **no** opencode; Get-BobAgentFuel has **no** opencode section | G1 Sync/rebuild |
| Chair skip MRB/UAT | #6134 merged | same binary lag | Heals with G1 |
| Digest OpenCode pcent | bobreport retain; ear publish missing | n/a | G2 = open **#6146** |
| TipForm OpenCode paint | zero hits | n/a | G2 = open **#6147** |
| Watchdog | 120s WaitForExit then kill+pause | opencode-out-of-fuel.log shows watchdog timeouts | G3 FR-OC-WATCHDOG |
| Turn lifecycle | no OpenCode turn watcher | n/a | G4 FR-OC-TURN |
| Inject/submit | ReadLine parent; child CreateNoWindow | n/a | G5 FR-OC-INJECT |
| Pack/Sync helpers | sources on main; Pack hits unclear | helpers absent on live fuel path | G6 FR-OC-PACK |
| Fleet auth smoke | setup skill on main | auth.json present on this box (presence only) | G7 FR-OC-FLEET |

## Non-gaps

- OpenCode seat/fuel/selection/wrapper core: already on main via PR #6121 / FR #6120 --- do not re-implement.
- Chair OpenCode skip hostile: FR #6134 --- do not re-implement.
- Digest logos / bob.ntsa.uk / ear-owns-publish: separate digest-ear-publish pack (#6141 closed; #6142-#6150 open).

## Evidence

- Live fuel JSON (no opencode key): install `tools\Get-BobAgentFuel.ps1`
- Live exe probe: `C:\ai\bob\worker\bob-worker.exe` ASCII lacks `opencode`
- Live false kills: `%LOCALAPPDATA%\Bobiverse\worker\logs\opencode-out-of-fuel.log`
- Main sources: `repo/bob/scripts/bob_worker.py`, `repo/common/scripts/opencode_fuel.py`, `repo/bob/tray/tools/Get-BobOpencodeFuel.ps1`
