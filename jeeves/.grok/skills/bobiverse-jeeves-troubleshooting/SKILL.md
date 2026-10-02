---
name: bobiverse-jeeves-troubleshooting
description: >
  Debug playbook for Jeeves/chair problems - command denials, empty queue, +h grant loops, webhook down alerts, roster/ChanServ, BobCallback permissions, DPAPI, NSSM. Use when the Jeeves chair, a webhook, or the roster misbehaves.
---

# bobiverse-jeeves-troubleshooting

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Start with `bobiverse-fleet-ops` (health checks, hotpatch rules, known-failure table). Jeeves-specific lessons:

| Symptom | Diagnosis / fix |
|---|---|
| Commands "do nothing" for the ear | The ear is only recognised as `bob-<machine>` for a machine on the roster. Check `!status roster:`; `!resync`; confirm the SASL account is logged in (`chan-privs` logs). |
| Replies never arrive | Replies go by PM (not the channel). The chair logs `git-help pm nick=... kind=ear`; `cmd-trace.log` has the text. Rate limit: `!help`/`!list` 30 s per nick. |
| `!list` says "queue empty" but `!status` has unaccepted items | `!focus strict on` hides everything not focused. `!focus strict off` (and restore afterwards). |
| `GRANT +h` repeated every 30-60 s | Not the chair: the ear is reconnecting. See the ear restart loop (missing `--host`). The chair caps at 3 grants/10 min then WARNs once; `removed by ChanServ` WARN = a ChanServ/AMODE fight. |
| `chanserv-sync timeout; keeping last good roster` | Two forced syncs overlapped or Ergo was slow; the last roster stays. Harmless once. |
| `ERROR chanserv LIST DENIED` | The Jeeves IRC oper lacks the `chanreg` capability (do not edit the Ergo config from here; tell the Ergo owner). |
| Webhook down alert in #bobiverse | `webhook-health.json` says which target/check. `local` down = `BobCallback` task not running (`schtasks /Run /TN BobCallback`, port 7700 free?). `public` down only = IIS site/ARR/rewrite (`Install-BobWebhooks.ps1`). |
| BobCallback cannot write the digest | The task runs as SYSTEM; the digest home must grant SYSTEM and the service user. Writes use unique `*.tmp` names and orphan cleanup; never delete `digest.json`. |
| `github_resync: no token` | Put the token in `config\github.token` (one line, ACL SYSTEM+Administrators). Handling is unchanged; only the source is logged. |
| Chair keeps losing the nick `Jeeves` | Legacy `BobJeeves` (gh-Jeeves) still installed - remove it from the SCM. |
| `error: the following arguments are required: --channel` | An unquoted `#bobiverse` in a PowerShell command line. Quote it. |
| Mojibake / parse failure in a ps1 | Keep the BOM on existing ps1 files; write Python/JSON/outbox without BOM. |
| After MSI, service still runs old code | NSSM Application path - re-run `Install-Jeeves.ps1`; check `<ai root>\jeeves\VERSION`. |
| Ergo restarted when the MSI upgraded | `ergo.exe` hard link (#70) - verify `fsutil hardlink list <ai root>\ergo\ergo.exe` shows ONE name; the installer repairs it without stopping Ergo. |

Always finish with the harvest step (see rule above) - every row here was learned the hard way and is only useful if the next
agent files what it finds.
