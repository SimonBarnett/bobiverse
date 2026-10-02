# Vision: bobiverse

## Objective

Fleet Windows boxes install single-file MSIs from `SimonBarnett/bobiverse` so Ergo+Jeeves, Bob ears, and airc consoles run as maintained services with ChanServ-backed shops, recycle/self-update, and agent skills for debug.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Three MSIs publish | `jeeves-*.msi`, `bob-*.msi`, `airc-*.msi` on a GitHub Release | `gh release view <tag> --repo SimonBarnett/bobiverse` lists all three assets | Missing any asset |
| S2 | `!register` + Bob modes | Registered `Bob-{mid}` gets +o on shop and +h on `#bobiverse` | `irc.log` shows MODE +o/+h after Bob JOIN | No modes or Bob self-REGISTER required |
| S3 | Recycle path | Systray Restart and `!recycle` restart `ircBob` with departure announce | Channel PRIVMSG + `Get-Service ircBob` Running | Tray-only restart leaves stale ear |
| S4 | Self-update | Service restart installs newer Release MSI | `<ai root>\bob\VERSION` (or jeeves/airc) bumps after restart | Stays on old bits when newer release exists |

LOCKED

## Shape

Primary (one): service

Hybrid note: Windows services + systray UI on Bob MSI; no customer website.

LOCKED

## Stack

Default: Python 3.12+ `irc_agent`, NSSM Windows services, WiX MSI, Ergo (Jeeves host only), PowerShell install/bootstrap, GitHub Releases.

Why: Matches live fleet (agentic_irc / airc-console) and approved plan.

Why-not: Cloud-only agents or Libera — fleet is private Ergo `irc.ntsa.uk`.

LOCKED

## Architecture

```
SimonBarnett/bobiverse Releases
  ├─ jeeves-*.msi → BobIrcd + ircJeeves (Ergo host)
  ├─ bob-*.msi    → ircBob + tray + Watch-AgentHealth
  └─ airc-*.msi   → Airc ({mid}_console)

Jeeves: !register shops; +o all; !recycle jeeves → update
Bob:    JOIN fleet+shop; listen !recycle; tray restarts ircBob
Airc:   JOIN #{mid} if registered else #{domain|workgroup}
```

LOCKED

## Screens

Systray is the Bob UI surface; HTML mocks document tray states for UAT later.

| id | file | state |
|----|------|-------|
| M1 | docs/mocks/home.html | primary |
| M2 | docs/mocks/empty.html | empty |
| M3 | docs/mocks/error.html | error |

## LOCKED

- Repo name `SimonBarnett/bobiverse`
- Services `ircJeeves`, `ircBob`, `Airc`, Ergo `BobIrcd`
- Nicks `Jeeves`, `Bob-{machinename}`, `{machinename}_console`, agents `{machine}-{pid}`
- Op registers via `!register`; Bob does not self-REGISTER shops
- Self-update via GitHub Release MSI on service start

## LOCKED (pack layout)

- Jeeves MSI stages Ergo under payload `ergo\` (`ergo.exe`, `default.yaml`, languages…).
  Install copies/seeds **`<ai root>\ergo`** and registers service **`BobIrcd`** (NSSM in Ergo root).
- Bob MSI stages **`Watch-AgentHealth\`** (Desktop install IF MISSING) + **`Start-BobTray.ps1`**.
  TipForm menu **Restart** → `Start-BobFleetTray -ForceNew` (restarts `ircBob` then relaunches tray).
  Ear-only shortcut: **Restart ircBob** / `Restart-BobEar.ps1`.
- `!recycle jeeves` restarts **`ircJeeves` only** (does not bounce `BobIrcd`).
