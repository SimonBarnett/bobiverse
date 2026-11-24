---
name: bobiverse-jeeves-agent-incident-report
description: >
  Turn a monitor, triage or seat-health finding into one de-duplicated bobiverse
  intake issue with a fixed body template, redaction, and rate-limited comments.
  Use for filing findings, twin search, or /bobiverse-jeeves-agent-incident-report.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-incident-report

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Public hosts only: bob.ntsa.uk, irc.ntsa.uk, github.com.

File only under `SimonBarnett/bobiverse` (never customer repos; never customer or
Priority wording). Related: BOB-42 stall detect (#8687), BOB-41 harvest (#8680).

## De-duplication (before filing)

Search open issues by fingerprint (test id, seat, route, machine, error token):

```powershell
gh search issues --repo SimonBarnett/bobiverse --state open "stdout.log stale"
gh search issues --repo SimonBarnett/bobiverse --state open "seats_stuck_doing machine:flamingo"
gh search issues --repo SimonBarnett/bobiverse --state open "BobModelsWebhook"
gh issue list -R SimonBarnett/bobiverse --state open --search "build-jeeves red main"
```

On a match: comment with new evidence only. **No twin.** Rate limit: if the same
fingerprint was filed or commented and nothing changed, do not re-file or re-comment.

## Body template (every section required)

1. **What** - one-line finding class
2. **Where** - machine / path / route / seat (public hosts only)
3. **Evidence** - redacted commands + output; times in Europe/London
4. **Suspected cause** - hypothesis vs confirmed
5. **Related FR numbers** - links
6. **Suggested fix** - owner (Si / FR / install ROLLBACK); no secrets

Redact before posting: tokens, passwords, webhook keys, NSSM env, `oper.cred`,
`identity.json`, PATs, personal profile paths.

## File command

```powershell
.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "<short>" -Body "<template>"
```

## Stop rules

- bobiverse repo only. Stop if the body still contains secret-shaped text after redaction.
- Never `!assign` / fake ACK/DONE from a filing path.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.