<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/bob-fleet-peer-peek.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Bob Fleet peer peek transport (2026-09-19)

**Not WinRM. Not a Windows service. Fail closed.**

The tray hover card lists **every registered fleet machine** even when this box cannot read a peer store. Jobs are never invented. A peer that cannot be read is a tile with `  unreachable` (or `  lastSeen stale` if the store is readable but the heartbeat is old and there are no jobs). The footer `other hosts not in this store` is only used when this box truly knows no peers.

## Canonical registry

Union, later sources overlay earlier:

1. Bundled `config/fleet-registry.json` — loaded when `BOB_BRIDGE_HOME` is the real `~\.grok\bob-bridge` (or `BOB_FLEET_BUNDLED=1`). Isolated Fake-Grok tests do not load it.
2. `{BOB_BRIDGE_HOME}\fleet\registry.json` — written by `Register-BobMachine` / heartbeat for **this** host (`id`, `hostname`, `bridgeHome`, `lastSeen`). Overlay `peekRoot` / extra machines here.
3. `$env:BOB_FLEET_REGISTRY` — optional extra JSON file (same shape).
4. Local `fleet\machines\*.json` and `machine.json`.

`$env:BOB_FLEET_SHARE` (or `shareRoot` in a registry file) is a folder where each host publishes `{id}.json` snapshots.

## What heartbeat writes (discoverable records)

On each fleet tick / `Register-BobMachine`:

- `{BOB_BRIDGE_HOME}\machine.json`
- `{BOB_BRIDGE_HOME}\fleet\machines\{id}.json`
- `{BOB_BRIDGE_HOME}\fleet\peek\{id}.json` — compact snapshot: `id`, `hostname`, `bridgeHome`, `lastSeen`, `running[]`, `inbox[]` (each job has `repo` stamped on the owning box)
- `{BOB_FLEET_SHARE}\{id}.json` when a share is configured
- stub `fleet\machines\{peer}.json` for bundled peers that are not in this store yet (so `Get-BobMachines` lists them)

## How hover peeks a peer (read-only)

For each registered id that is **not** this host, try in order, each I/O wrapped in a timeout (`peekTimeoutMs`, default 1500ms):

1. Explicit `peekRoot` (directory = peer `BOB_BRIDGE_HOME`, or a `.json` snapshot file).
2. `{shareRoot}\{id}.json`.
3. Do **not** auto-probe `\\hostname\C$` from the tray (DNS/SMB misses freeze idle hover). Cross-host status is the `#bobiverse` MODE2 moot (`docs/bobiverse.md`): `BOB v1` POINT lines, `reach=irc-fallback`. `peekRoot` / `BOB_FLEET_SHARE` remain optional. No `Invoke-Command`. No WinRM. No SMB.

First successful read wins. Snapshot file `fleet\peek\{id}.json` is preferred; else `machine.json` plus `fleet\running\{id}\*.json` and `fleet\inbox\{id}\*.json`.

Fail closed:

| Result | Tile |
|---|---|
| This host | local jobs, or `  no jobs` |
| Peer jobs already in **this** store | show those jobs (`reach=ok`) |
| Peek ok, jobs present | nest jobs; if heartbeat older than `staleAfterSec` also print `  lastSeen stale` |
| Peek ok, zero jobs, lastSeen fresh | `  no jobs` |
| Peek ok, zero jobs, lastSeen missing/old | `  lastSeen stale` |
| Peek fail / timeout / DNS miss | `  unreachable` (no job lines) |

Do not call `git` against a peer cwd (wrong box). Use the stamped `repo` field.

## Enable live cross-host jobs

Isolated boxes (ionos public VPS vs MarchHare LAN) will **not** resolve each other’s hostnames. Then every tray still shows all registry tiles; peers stay `  unreachable` until one of:

```powershell
# A. Shared folder both boxes can write/read (Syncthing, mapped drive, existing NAS)
[Environment]::SetEnvironmentVariable('BOB_FLEET_SHARE', 'S:\bob-fleet-peek', 'User')

# B. Per-peer overlay on this box (local path or UNC that already works)
# {BOB_BRIDGE_HOME}\fleet\registry.json
# { "machines": [ { "id": "marchhare", "peekRoot": "\\\\MarchHare\\C$\\Users\\Administrator\\.grok\\bob-bridge" } ] }
```

Then recycle **Watch-BobTray.ps1 only**. Never `Stop-ScheduledTask BobFleet-*` while jobs run.

## Cmdlets

`Get-BobFleetRegistry` — merged machine list + transport settings.  
`Get-BobTrayHover` — `scope=fleet-peek` when any peer is registered; `machines[].reach` is `local|ok|stale|unreachable`.
