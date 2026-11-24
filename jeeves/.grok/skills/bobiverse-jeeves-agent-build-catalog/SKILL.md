---
name: bobiverse-jeeves-agent-build-catalog
description: >
  Add or edit builds-catalog.json entries safely: backup plus ROLLBACK.ps1 first,
  validate schema from builds_catalog.py, confirm the recipe yml exists at ref,
  then re-check local and public /bob/v1/builds routes. Use for !build catalog
  edits, FR #8490 / #8770 follow-up, or /bobiverse-jeeves-agent-build-catalog.
depends_on:
  - bobiverse-jeeves-agent-monitor
  - bobiverse-build
---

# bobiverse-jeeves-agent-build-catalog

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Catalog file (digest home on walrus): `C:\Users\Administrator\.bobiverse\builds-catalog.json`.
Served at `http://127.0.0.1:7700/bob/v1/builds` and `https://bob.ntsa.uk/bob/v1/builds (prefer over irc.ntsa.uk off-LAN)`
(IIS rule `BobBuildsWebhook`). Schema and numbering: `common/scripts/builds_catalog.py`.
Recipe/announce rules: `bobiverse-build`. Post-check: `bobiverse-jeeves-agent-monitor` step 6.
**Catalog edits only on Si's go.** No Jeeves restart. Never `!build cancel`.

## Entry schema

| Field | Meaning |
|---|---|
| name | Display name |
| yml | `owner/repo` or `owner/repo:path` (default `.bobiverse/build.yml`) |
| output | Build output directory |
| install | `fleet` or one lowercase machine id |
| dep | Documentation only |
| version | `""` = operator types it; else numeric `x.y.z` |
| ref | Git ref (e.g. `main`) |

JSON must parse as an **array** before saving. Entries are numbered 1..n in file order.

## Steps

1. Confirm Si's go for this edit. Refuse otherwise.
2. Backup first:
   `C:\ai\jeeves\_backup-builds-catalog-<yyyyMMdd-HHmmss>\` holding the current
   `builds-catalog.json` plus a `ROLLBACK.ps1` that copies it back (no service restart).
3. Validate the proposed entry fields. Reject (or warn and mark "nothing started") when the
   recipe yml (github.com contents API) is missing at `ref`:
   `gh api repos/<owner>/<repo>/contents/<path>?ref=<ref>` (host gh auth only; never echo tokens).
4. Write the array only after `ConvertFrom-Json` round-trips as an array.
5. Re-check both routes; report previous and new entry counts:
   `(Invoke-WebRequest http://127.0.0.1:7700/bob/v1/builds -UseBasicParsing).Content`
   `(Invoke-WebRequest https://bob.ntsa.uk/bob/v1/builds (prefer over irc.ntsa.uk off-LAN) -UseBasicParsing).Content`
   Public empty but local not = missing IIS rule `BobBuildsWebhook`. Both empty = file missing/invalid.
6. Report: backup folder, entry name/yml/ref, counts, route status codes. No restart.

## Stop rules

- No Si go: stop with the drafted ask.
- Schema/recipe failure: leave the previous file in place (or run ROLLBACK.ps1).
- Never restart `ircJeeves` for a catalog edit.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.