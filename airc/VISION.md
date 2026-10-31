# Vision: airc (console)

Product folder: `airc/` in `SimonBarnett/bobiverse`. Fleet umbrella: `common/docs/vision.md`.
This file is the **airc-product** vision for MRB/UAT vision-first judgement (FR #4158; bob parity FR #1615).

## Objective

Every fleet Windows box that needs remote shell runs a maintained **Airc** console service so operators can reach `{MachineId}_console` on the registered shop `#{MachineId}` (or `#wonderland` fallback) without inventing Ergo PASS, leaking secrets, or leaving a second `AircConsole` tree.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Console present | `Airc` Running; nick `{mid}_console` on control channel | `Get-Service Airc`; console log `chanserv-info` / JOIN; `airc.exe --selftest` when staged | Service stopped or nick not joined |
| S2 | Shop vs wonderland | Registered `#{mid}` -> shop; else `#wonderland` (never `#{domain\|workgroup}`) | FR #3834; log `control-channel=... reason=registered-machine\|wonderland-fallback`; probe timeout still logs `chanserv-probe timeout -> wonderland` (FR #4014); `test_fr3834_wonderland_control_channel.py` | Joins domain/workgroup lobby; missing wonderland substring after timeout rewrite |
| S3 | Remote shell wire | STATUS/Command get `out id= seq=` then `DONE id= exit=`; oversized output may use reverse DCC/TLS (`DONE ... via=dcc`) when caller sent `DCCLISTEN` with optional `tls=`/`relay=` (FR #5003 / #5008), else IRC CONT pages; ops/half-ops auth on control channel | FR #75 / #2570 / #3401 / #5003 / #5008; `Invoke-AircRemote`; `airc/tests` shell framing + dcc bulk | Bare STATUS with empty StdOut; `DONE exit=126 not-op` for live +o/+h wrongly denied; secrets on IRC; multi-KB dumps only on IRC flooding Ergo |
| S4 | Identity on upgrade | MSI upgrade keeps ConsoleHome / MachineId from live AppParameters (then airc-install.json) | FR #1552; Install reads NSSM AppParameters first; no Default\.airc invent | SASL 904 / NickServ 433 after upgrade from fresh home invent |
| S5 | CAST IRON harvest | Every gap/skill filed same turn via intake | `Report-BobiverseIntakeIssue.ps1`; airc skills lead with harvest rule | Findings left unfiled |

LOCKED

## Shape

Primary (one): service

Hybrid note: Windows service **Airc** (NSSM, optional frozen `airc.exe`) is the product core; `Invoke-AircRemote.ps1` is the driving-box helper (not a website). Fleet vs client/workstation MSI profiles change capabilities, not the product shape.

LOCKED

## Stack

Default: Python `airc_console` / `airc_console_service.py` (PyInstaller `airc.exe`), PowerShell install/start (`Install-Airc`, `Start-AircConsole`), NSSM `Airc`, WiX airc MSI, private Ergo `irc.ntsa.uk`.

Why: Matches live fleet install trees under `<ai root>\airc` and session-0 MSI upgrades.

Why-not: Public Libera or a second agentic_irc `AircConsole` tree on the same box --- one console per machine.

LOCKED

## Architecture

```
Invoke-AircRemote (driving box)
  └─ PRIVMSG / Query via bob ear outbox -> {mid}_console
       └─ DONE id= exit=  (ReplyFile: bob home airc-replies.jsonl)

Airc service (NSSM)
  ├─ nick {MachineId}_console; SASL (GUID in ConsoleHome\console.password)
  ├─ Ergo PASS in config\ergo.password (never invent)
  ├─ control channel: #{MachineId} if registered else #wonderland (FR #3834)
  ├─ presence JOIN is opt-in (FR #5190: client never auto-joins #bobiverse)
  ├─ shell / jobs / update capabilities (AIRC_* / airc.json; Bob fleet shell default ON FR #4030)
  ├─ auth: live +o/+h/+a/+q on control only (no operators.txt roster)
  └─ isolated long jobs: NEW worker process/instance **in the airc service deployment**
       (import modules / scripts from `<ai root>\airc`  -  no peer product binaries)

Install / upgrade
  ├─ AppParameters preserve ConsoleHome (FR #1552)
  ├─ fleet | client | workstation profiles (agent layer / allow-list / purge)
  └─ self_update detached Update-BobiverseService (never inline msiexec)
```

Trust: no secrets in filings/logs; Ergo PASS / NickServ GUID stay in config/ConsoleHome with Protect-BobiverseSecretPath ACLs. Hotpatch restarts **Airc** only; never touch Ergo / `BobIrcd`.

**CAST IRON  -  isolated workers (operator 2026-10-31):** every isolated process started from airc code for verbs such as UPDATE helpers, EXTENSION, NETWORK, LEGION, Priority Client must be **deployed as part of the Airc service tree** (module import or service-owned child running airc-packaged code). **No separate product binaries** (`*Client.exe`, `*Worker.exe`, peer installers as the verb runtime). Offline/manual tools already in MSI (e.g. historical `airc-network-installer.exe`) may remain for non-verb use; console verbs must not depend on them as the implementation path. See `docs/airc-isolated-workers-in-service.md`.

LOCKED

## Screens

Airc has no TipForm UI. Operator surfaces are service logs, `Invoke-AircRemote`, and ear Query replies. HTML mocks are out of scope until a status site is chosen (see UNKNOWN).

| id | file | state |
|----|------|-------|
| (none) | --- | no design-uat mocks yet |

## LOCKED

- Product path `/bobiverse/airc`; install `<ai root>\airc`; service name `Airc` (not `AircConsole`)
- Console nick `{MachineId}_console`; MachineId = lowercase sanitized fleet id
- Control channel: registered `#{MachineId}` else `#wonderland` (FR #3834); timeout log keeps `chanserv-probe timeout -> wonderland` (FR #4014)
- Never invent Ergo PASS; never invent ConsoleHome on upgrade when AppParameters exist (FR #1552)
- CAST IRON harvest + intake every session; never print secrets
- Hotpatch: never touch Ergo / `BobIrcd`; restart only `Airc`
- One console per box: Install removes leftover `AircConsole` from SCM
- CAST IRON isolated workers: **in-service deployment only**  -  no separate product binaries for verb runtimes (EXTENSION / NETWORK / LEGION / Priority / similar); see `docs/airc-isolated-workers-in-service.md`

## UNKNOWN

- Future HTML / TipForm-style status surface for console health (logs + Invoke-AircRemote remain primary)
- Exact ChanServ probe timing under heavy Ergo load beyond FR #3834 / #4014 fallbacks
- Client `presence_channels` stay empty unless an operator opts in (FR #5190)
