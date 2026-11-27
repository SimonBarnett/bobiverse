---
name: bobiverse-jeeves-agent-main-red
description: >
  When build-jeeves fails on main: find the first bad commit and failing test,
  name the introducing PR, file one de-duplicated issue, and point installs at
  the last green commit. Use for red main, last green install SHA, or
  /bobiverse-jeeves-agent-main-red.
depends_on:
  - bobiverse-jeeves-agent-build
---

# bobiverse-jeeves-agent-main-red

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Companion to `bobiverse-jeeves-agent-build` ("Never build from red main").
gh auth (github.com host login) only; never echo tokens. Never compile locally
or on MarchHare, never push/merge, never re-run workflows in a loop.

## Steps

1. List recent main push runs:
```powershell
gh run list -R SimonBarnett/bobiverse --workflow build-jeeves.yml --branch main --event push --limit 20 --json databaseId,headSha,conclusion,createdAt,displayTitle,url
```
2. Newest `success` = last green (record sha + run id + url). Newest failure above it =
   red HEAD window. Commits between last green and first red are the suspect range
   (`gh api repos/SimonBarnett/bobiverse/compare/<green>...<red>`).
3. From the oldest failing run log, name the failing test id
   (`gh run view <id> -R SimonBarnett/bobiverse --log-failed`). Map the first bad
   commit to its PR (`gh pr list -R SimonBarnett/bobiverse --search <sha> --state merged`).
4. De-dup then file exactly one issue (comment if a twin exists) with the run URL as evidence.
   Intake: `Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse`.
5. Point installs at the last green commit (hand the sha + run id to
   `bobiverse-jeeves-agent-install` / build receipt). Say what that green build contains or lacks
   relative to HEAD (e.g. missing later fixes).

## Worked example (21 Nov 2026)

HEAD red on `test_process_intake_harvest_stub_logs_draft_pr_unsupported` since PR #8644;
installs used `b5f8f0bc` (run `44909235948`, success), which contained PR #8491.

## Report

- first bad commit + PR
- failing test id
- last green sha + run id (+ url)
- what that green build contains or lacks vs HEAD
- intake issue number (or twin comment)

## Stop rules

- Stop after one filing; do not loop `gh run rerun`.
- Never install from red HEAD; never compile on MarchHare.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.