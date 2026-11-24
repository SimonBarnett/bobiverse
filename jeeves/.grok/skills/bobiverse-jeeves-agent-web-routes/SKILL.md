---
name: bobiverse-jeeves-agent-web-routes
description: >
  Document and check the IIS front door on walrus (site irc-ntsa) rewrite rules
  to 127.0.0.1:7700 for report, digest, git, intake, jira, builds, hours, models
  and the /jeeves appliance; compare local, LAN and public hosts. Use for IIS
  webhook routes, 502/404 on bob.ntsa.uk, or /bobiverse-jeeves-agent-web-routes.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-web-routes

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

IIS site `irc-ntsa` on walrus binds public hosts `bob.ntsa.uk` and `irc.ntsa.uk`
(and the IRC WebSocket front on port 7999). Rewrite rules target `http://127.0.0.1:7700`.
Source of truth for rule names: `jeeves/scripts/Install-BobWebhooks.ps1`.
IIS changes only via that script with a backup, and **only on Si's go**.
No webhook keys or secrets in checks. No public DNS changes from this skill.

## Route table

| Path | IIS rule | Backend | Expected |
|---|---|---|---|
| `/bob/v1/report` | BobReportWebhook | `127.0.0.1:7700/bob/v1/report` | 200 JSON |
| `/bob/v1/digest` | BobDigestWebhook | redirect to report | 301/200 |
| `/bob/v1/git` | BobGitWebhook | `.../bob/v1/git` | 200/4xx per auth |
| `/bob/v1/intake` | BobIntakeWebhook | `.../bob/v1/intake` | 200/4xx |
| `/bob/v1/jira` | BobJiraWebhook | `.../bob/v1/jira` | 200/4xx |
| `/bob/v1/builds` | BobBuildsWebhook | `.../bob/v1/builds` | 200 JSON array |
| `/bob/v1/hours` | BobHoursWebhook | `.../bob/v1/hours` | 200/4xx |
| `/bob/v1/models` | BobModelsWebhook | `.../bob/v1/models` | 200 (see #8766 if HTML 404) |
| `/jeeves` | BobJeevesAppliance | `.../jeeves` | 200 UI |
| IRC WebSocket :7999 | site WS rules | local WS backend | LAN use |

Check three places: local `http://127.0.0.1:7700/...`, LAN via `irc.ntsa.uk`, public via `https://bob.ntsa.uk/...`.
Never print response bodies that may contain secrets; status + content-type + length are enough.

## Host choice (21 Nov / 24 Nov evidence)

- Prefer **`https://bob.ntsa.uk`** from off the LAN (public).
- `irc.ntsa.uk` may answer on the LAN and can time out from outside (observed 21 Nov ~19:25 GMT off-LAN timeout on report/builds). From flamingo (LAN) on 24 Nov both `bob.ntsa.uk` and `irc.ntsa.uk` `/bob/v1/report` returned 200.
- Document timeouts as DNS / port-forward / edge policy - file only if still reproducible off-LAN; do not change DNS here.

## Missing rule

Report the **exact** rule name (e.g. `BobModelsWebhook`, `BobBuildsWebhook`). Fix path: re-run
`Install-BobWebhooks.ps1` on walrus after backup, Si's go only. Never hand-edit live `web.config`
without the script + ROLLBACK.

## Stop rules

- No secrets in output. No Cloudflare/DNS edits for any jeeves host.
- Stop before any IIS mutate without Si's OK.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.