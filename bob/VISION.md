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
| S3 | Inject submits | Jeeves `FROM` lines auto-submit in the TUI (no manual Enter) | `inject_console` gap ≥ 0.20s + double Enter; submit-verify probe + Enter-only retry never re-paste (FR #2696); `test_fr1601_inject_submit_gap.py` + `test_fr2696_inject_submit_verify.py` | Line sits waiting for Enter (`relay: injected` but agent idle; no `submit-verify ok` / retries exhausted) |
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
  ├─ relay: paste/WriteConsoleInput FROM lines (submit gap + Enter×2 + submit-verify Enter-only retry, FR #2696)
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
- Event-driven inject/relay; submit gap (`BOB_WORKER_SUBMIT_GAP_S`, default 0.20s) + second Enter; submit-verify probe + Enter-only retry never re-paste (FR #2696, `BOB_WORKER_SUBMIT_VERIFY*`)
- Shop wire: program `!bored` after harvest hold on DONE/NACK/GIVEUP (FR #1611); agent ACK/DONE/NACK/GIVEUP on `#{machine}` only
- CAST IRON harvest + intake every session (before the program's next `!bored`); never print secrets
- Hotpatch: never touch Ergo / `BobIrcd`; restart only the product service concerned

## UNKNOWN

- Exact Cursor/Grok TUI paste-mode timing across all host console types (Windows Terminal vs conhost) beyond FR #1601 defaults; first-paste race mitigated by FR #2696 submit-verify on grok (cursor still has no durable enqueue probe)
- Future HTML status site (tray remains primary UI)
