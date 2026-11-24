---
name: bobiverse-jeeves-agent-logs
description: >
  Map where Jeeves logs live on walrus, give safe Tail/Select-String patterns,
  convert UTC stamps to Europe/London, and investigate stale stdout.log without
  reading NSSM env or credentials. Use for log locations, channel-sync greps,
  or /bobiverse-jeeves-agent-logs.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-logs

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Read-only log map for the Jeeves agent. Public hosts only: bob.ntsa.uk, irc.ntsa.uk, github.com. Health context: `bobiverse-jeeves-agent-monitor`.
Walrus install root `C:\ai\jeeves` (= share `Jeeves` / `J:`). Chair home default
`C:\Users\Administrator\.jeeves`; digest home default `C:\Users\Administrator\.bobiverse`
(installer may override; resolve from live layout, do not invent paths).

## Log table (walrus checked 24 Nov 2026)

| Path | Holds | Timestamped | Rotation / write notes |
|---|---|---|---|
| `C:\ai\jeeves\logs\stdout.log` | NSSM `AppStdout` for `ircJeeves` (chair INFO lines, `channel-sync`, outbox sends) | Line stamps often absent; use file `LastWriteTimeUtc` | Installer sets `AppStdout`; **no** `AppRotate*` params observed - file can grow large (64 MB on check day) |
| `C:\ai\jeeves\logs\stderr.log` | NSSM `AppStderr` | Same | Same; smaller |
| `C:\Users\Administrator\.jeeves\cmd-trace.log` | Timed command trace (preferred when stdout looks stale) | Yes (trace lines) | Chair home; advances while HTTP health stays fresh |
| `C:\Users\Administrator\.jeeves\webhook-health.json` | Webhook target up/down snapshot | File mtime | JSON state, not a tail log |
| `C:\Users\Administrator\.jeeves\stall-filer.json` | Stall-filer state | File mtime | May stay quiet when healthy |
| `C:\Users\Administrator\.bobiverse\digest.json` | Fleet digest | `ts` / mtime | Must agree with `/health` `last_digest_write` |

NSSM registry (read param **names** only via `nssm get ircJeeves AppStdout` etc., never
`AppEnvironmentExtra` / `AppParameters`): on 24 Nov 2026 walrus,
`Application=C:\ai\jeeves\.\jeeves\jeeves.exe`,
`AppStdout=C:\ai\jeeves\.\logs\stdout.log`,
`AppStderr=C:\ai\jeeves\.\logs\stderr.log`, no `AppRotateFiles` / `AppRotateBytes`.

## Stale stdout.log investigation (issue evidence)

Observed 21 Nov 2026 ~14:52 GMT: `stdout.log` stopped updating just after a 14:51 restart while
`/health` stayed fresh. Re-check 24 Nov 2026 22:22 UTC (read-only WinRM): path still
`...\logs\stdout.log`, writes resumed (LastWriteTimeUtc 22:13 UTC, length ~64 MB),
`cmd-trace.log` and digest `last_digest_write` fresh, `/health` `ok:true`, free disk ~157 GB.
Service PID (NSSM parent) differs from `/health` `pid` (child `jeeves.exe`) - normal.

**Root cause class for the 21 Nov episode:** not a moved `AppStdout` path and not disk-full.
`/health` runs on a daemon thread and does not prove IRC/stdout progress; `irc_agent.info`
can swallow stdout `OSError`. Treat "fresh health + stale stdout" as a chair-progress finding:
use `cmd-trace.log` + digest age, file via intake, do **not** restart without Si's OK.
Also file/keep open the missing `AppRotate*` gap (unbounded growth). Evidence folder:
quote commands + redacted output in the PR / `jeeves/docs/evidence/`.

Hypotheses checklist (confirm with evidence only): H1 path moved; H2 external rotation;
H3 Application not `jeeves.exe`; H4 disk/write failure; H5 chair stall with HTTP alive.

## Safe read patterns

Metadata first:
```powershell
Get-Item C:\ai\jeeves\logs\stdout.log, C:\ai\jeeves\logs\stderr.log,
  C:\Users\Administrator\.jeeves\cmd-trace.log,
  C:\Users\Administrator\.bobiverse\digest.json |
  Select-Object FullName, Length, LastWriteTimeUtc
```

Bounded tail then filter (never dump whole files; never touch `inbound-transcript.log`):
```powershell
Get-Content C:\ai\jeeves\logs\stdout.log -Tail 80 | Select-String 'channel-sync registered='
Get-Content C:\Users\Administrator\.jeeves\cmd-trace.log -Tail 120 | Select-String 'outbox: sent PRIVMSG|ERROR|WARN'
(Get-Content C:\ai\jeeves\logs\stdout.log -Tail 200 | Select-String 'ERROR|WARN').Count
```

## Times

Convert UTC to Europe/London with `[TimeZoneInfo]::FindSystemTimeZoneById('GMT Standard Time')`
and `[TimeZoneInfo]::ConvertTimeFromUtc` - no fixed offset. GMT equals UTC outside British Summer Time.

## Stop rules

- Never open NSSM env values, `oper.cred`, `identity.json`, `_backup-nssm-env-*`, passwords folders.
- Never restart `ircJeeves` or change NSSM log paths without Si's OK + backup + ROLLBACK.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.