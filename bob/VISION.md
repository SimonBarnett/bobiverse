# Vision: bob (ear, tray, worker)

Product folder: `bob/` in `SimonBarnett/bobiverse`. Fleet umbrella: `common/docs/vision.md`.
This file is the **bob-product** vision for MRB/UAT vision-first judgement (FR #1615).

## Objective

Every fleet Windows box runs a maintained **ircBob** ear plus TipForm tray and **bob-worker** seats so shop work (FR/MRB/UAT) flows on `#{machine}` without manual Enter, self-REGISTER, or secret leakage.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Ear present | `ircBob` Running; nick `Bob-{mid}` on `#bobiverse` + `#{mid}` | `Get-Service ircBob`; `bob/home/irc.log` JOIN lines | Service stopped or shop not joined |
| S2 | One-window worker | Tray **Agent** starts one `bob-worker.exe` = one console = one agent | `pytest bob/tests/test_bob_worker_020.py` one-window cases; no `CREATE_NEW_CONSOLE` for agent | Second console / orphan agent |
| S3 | Inject submits | Jeeves `FROM` lines land as one paste (not per-char drip) and auto-submit | clipboard+Ctrl+V (FR #2498) then gap ≥ 0.20s + double Enter (FR #1601); `test_fr2498_inject_paste.py` / `test_fr1601_inject_submit_gap.py` | Drip-typing (~2 min/assign) or line waits for Enter |
| S4 | Shop wire | Program posts `!bored` (after DONE/NACK/GIVEUP harvest hold, FR #1611); agent writes ACK/DONE only to `#{mid}` outbox | `bobiverse-bob-job-irc`; worker.log `bored -> shop` / `harvest-hold` | Model posts `!bored` or PRIVMSG nick/`#bobiverse`; immediate `!bored` before harvest |
| S5 | CAST IRON harvest | Every gap/skill filed same turn via intake | `Report-BobiverseIntakeIssue.ps1`; AGENTS.md / skills lead with harvest rule | Findings left unfiled |

LOCKED

## Shape

Primary (one): service

Hybrid note: Windows service **ircBob** is the product core; TipForm systray and `bob-worker.exe` consoles are the operator/agent surfaces (not a website).

LOCKED

## Stack

Default: Python `irc_agent` / `bob_worker.py` (PyInstaller `bob-worker.exe`), PowerShell tray (`Start-BobFleetTray`), NSSM `ircBob`, WiX bob MSI, private Ergo `irc.ntsa.uk`.

Why: Matches live fleet install trees under `<ai root>\bob` and the composed flat runtime.

Why-not: Cloud-only agents or public Libera — shops and digests are Ergo + Jeeves.

LOCKED

## Architecture

```
TipForm tray
  ├─ Restart → ircBob recycle (+ Sync/ff on start)
  ├─ Agent  → bob-worker.exe --mode agent  (CWD bob/worker)
  └─ Plan   → bob-worker.exe --mode plan   (CWD bob/plan)

bob-worker.exe (one window)
  ├─ IRC seat nick {machine}-{pid} → JOIN #{machine} only
  ├─ relay: WriteConsoleInput FROM lines (submit gap + Enter×2)
  ├─ outbox.txt ← agent ACK/DONE/NACK/GIVEUP / PRIVMSG #{machine}
  └─ program posts !bored; never the model

ircBob ear
  ├─ Nick Bob-{machine}; JOIN #bobiverse + #{machine}
  ├─ digest report, recycle, outbox PRIVMSG (incl. airc)
  └─ never self-REGISTER shop (Jeeves !register only)
```

Trust: no secrets in filings/logs; Ergo PASS / NickServ / tokens stay in home/config files. Worker speaks only on its shop channel.

LOCKED

## Screens

Tray is the bob UI surface. HTML mocks document tip states for visual UAT later (`design-uat`).

| id | file | state |
|----|------|-------|
| M1 | bob/mocks/home.html | primary — tip with worker lines |
| M2 | bob/mocks/empty.html | empty — idle / no workers |
| M3 | bob/mocks/error.html | error — digest/hover stale |

## LOCKED

- Product path `/bobiverse/bob`; install `<ai root>\bob`
- Ear nick `Bob-{machinename}`; worker nick `{machine}-{pid}`
- Always-new agent (no `--resume` / `--continue`); one window per seat
- Event-driven inject/relay; submit gap (`BOB_WORKER_SUBMIT_GAP_S`, default 0.20s) + second Enter
- Shop wire: program `!bored` after harvest hold on DONE/NACK/GIVEUP (FR #1611); agent ACK/DONE/NACK/GIVEUP on `#{machine}` only
- CAST IRON harvest + intake every session (before the program's next `!bored`); never print secrets
- Hotpatch: never touch Ergo / `BobIrcd`; restart only the product service concerned

## UNKNOWN

- Exact Cursor/Grok TUI paste-mode timing across all host console types (Windows Terminal vs conhost) beyond the FR #1601 defaults
- Future HTML status site (tray remains primary UI)
