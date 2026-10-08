---
name: bobiverse-jeeves
description: >
  Maintain and debug the Jeeves chair (ircJeeves) and its webhooks on the Ergo host. Architecture, paths, ports, config, logs, background jobs (webhook health, GitHub resync), install/upgrade/hotpatch. Use in <ai root>\jeeves or for Jeeves service, !register, ChanServ, BobCallback, intake, or /bobiverse-jeeves.
---

# bobiverse-jeeves

## Keep the flow of work to the workers going

**Keep the flow of work to the workers going.** You are the **MONITORING** agent for the deterministic Jeeves service (not the chair, not a worker). Report delays via intake, de-duplicated against open issues: idle seat, empty offer queue, NAK/wait gates, GIVEUP loops, stale digest, open issues not offered/queued, self-review (pairing) blocks, stuck accepted rows, Jeeves/IRC/webhooks down. Never `!assign` / `!focus`; never touch Ergo/BobIrcd; no secrets.


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

Foundation: `bobiverse-fleet-ops` (shared ops/hotpatch/health) and `harvest` -> https://github.com/SimonBarnett/bobiverse

## Architecture

One issue per issue: when MRB (or any worker) finds a twin/duplicate issue, close the later one and comment a reference to the first; never leave both open; done issues are closed too.

`ircJeeves` runs `irc_agent.py --chair --nick Jeeves --home <chair home>` (NSSM, `Start-Jeeves.ps1`). Everything is
deterministic and token-less except the optional GitHub token used for filing issues and the hourly / webhook-gap FR/MRB resync (FR #3212; webhooks are the source of truth).

| Piece | Where |
|---|---|
| Install root | `<ai root>\jeeves` (`scripts\`, `config\`, `logs\`, `docs\`, `.grok\skills\`, `assets\`, `VERSION`) |
| Chair home (identity, queue, focus/ignore, traces) | `~\.jeeves`, else `C:\Users\Administrator\.jeeves`, else `<ai root>\jeeves\home-jeeves` (never `C:\Users\Default`) |
| Digest home (`digest.json`, `registered-machines.json`, `chair-outbox.txt`, `webhook-queue`) | `BOB_DIGEST_HOME` = `~\.bobiverse` |
| Ergo (IRC server, separate service `BobIrcd`) | `<ai root>\ergo` - NEVER edit `ircd.yaml`, never restart for non-Ergo work |
| Webhook receiver | task `BobCallback` (SYSTEM) `python scripts\bobcallback.py --home <digest home> --bind 127.0.0.1 --port 7700` |
| Public webhooks | IIS site `irc-ntsa` (`C:\inetpub\irc-ntsa\web.config`, written by `Install-BobWebhooks.ps1`): `/bob/v1/report`, `/digest`, `/git`, `/intake`, `/jira`, `/hours` (FR #3450) -> 127.0.0.1:7700 |
| Ports | 6697 TLS (public), 6667 plaintext loopback, 7700 bobcallback loopback |
| Logs | `<ai root>\jeeves\logs\stdout.log` / `stderr.log` (INFO/WARN/ERROR, no timestamps - use the chair `cmd-trace.log` for timed command replies) |
| Chair-home files | `cmd-trace.log` (time/nick/command/reply), `webhook-health.json`, `resync-token-source.log`, `operators.txt`, `identity.json` (DPAPI) |
| Config (`<ai root>\jeeves\config`) | `ergo.password`, `service.password`, `github.token` (optional), `op-accounts.txt`, chair oper cred (DPAPI), `autoupdate.disabled` |

Modules worth knowing: `irc_agent.py` (client + chair), `chair_commands.py` (command registry/auth/help),
`focus_ignore.py`, `gitclaim.py` (queue + `resync_from_github`), `chan_privs.py` (op/halfop grants + hard cap),
`registered_machines.py` (ChanServ roster mirror), `bobreport.py` (digest + chair outbox), `bobcallback.py` (webhooks),
`intake.py` (intake + filing), `bobhours.py` (FR #3450 hours webhook — timesheet source entries; no Priority write), `chair_health.py` (background jobs), `bob_recycle.py`.

**Living architecture FR (harvest #1989 / FR #1993):** approved ionos chair plans (e.g. `jeeves.exe` chair+HTTP one process, self-test/heal) are filed as **one** SimonBarnett/bobiverse FR with `require_machine: ionos` (and `needs-ionos` when stamped). Append WP evidence to **that same FR body** — do not open twin FRs per WP. Product work stays on #1993 until merged.

## Chair background jobs (inside ircJeeves, no extra task)

1. **Webhook health probe, every 30 min** (`chair_health.probe_cycle`): for BOTH `http://127.0.0.1:7700` and
   `https://irc.ntsa.uk` it checks `GET /bob/v1/report` (200), `GET /bob/v1/jira` (200), `GET /bob/v1/intake/<id>` (404 counts
   as up) and a synthetic `POST /bob/v1/git` ping (zen `jeeves-health-probe`, answered 204 with no queue entry and no
   announce). One retry before calling a target down. Each run is logged (`INFO webhook-health ...`); state is
   `webhook-health.json`; `#bobiverse` is told ONLY on up<->down transitions (`WEBHOOK DOWN ...` / `WEBHOOK RECOVERED ...`)
   through `chair-outbox.txt`.
2. **GitHub resync, hourly + webhook gap** (FR #3212; was 15 min): `gitclaim.resync_from_github` via `chair_health` /
   `github_api_budget` (ETag/304 conditional GETs, hourly call budget, backoff floor). Authenticated with the existing
   Jeeves token from `config\github.token` via `gh_filer`; token handling is unchanged and the value is never logged - only
   the token SOURCE is written once per process to `resync-token-source.log`. **Webhooks update the queue with zero REST** (including `issues`/`pull_request` `labeled`/`unlabeled` label mutations — FR #3275);
   reconcile is the exception path (startup, gap in deliveries, or hourly). It MERGES: open issues -> FR, open PRs -> MRB;
   closed/superseded FR/MRB rows of successfully fetched repos are dropped; accepted jobs, other kinds, failed repos and
   ignored repos are untouched; 403/401/429/5xx never purge. `!bored` is local-state only (budget 0). Repos:
   `JEEVES_RESYNC_REPOS` / `resync-repos.txt` in the chair home, else repos already queued + the token's own repos under the
   allowed owners. `!resync` runs it now; `!status` shows `github_resync:`, `webhooks:`, and `github-api:` remaining.
   **Open-PR MRB vs stale `mrb_done` (FR #1585 / harvest #1613):** premature `mrb_done` must not purge an MRB whose GitHub pull is still **open**. `mrb_already_done(..., pr_exists=)` treats open `pr_exists` as winning (keep/requeue the MRB); resync clears stale `mrb_done` stamps the same way it heals stale `fr_done`. Merged PR #1606.

**Offer order (FR #3205):** within focus priority, hand out **MRB then UAT then FR**, **lowest issue/PR number** first (not queue `seq` / arrival order). Same-priority repos interleave by kind then number (repo name is the final tie-break — not focus timestamp). A seat that cannot take waiting MRB/UAT rows still gets the next eligible FR (never `nothing queued` while one exists). `rebuild_offer_precompute` (resync / after offer stamp) writes `offer-precompute.json`; when its fingerprint matches the queue, `!bored` uses **zero** live GitHub calls (FR #3188 budget of 1 remains when precompute is stale).

## Services and identity

- `ircJeeves` (nick **Jeeves**) and `BobIrcd` (Ergo). Legacy `BobJeeves` (gh-Jeeves) must be removed from the SCM: it fights for the nick.
- **ObjectName must be the install user** (DPAPI) - not LocalSystem. Quiet MSI: `BOBIVERSE_SERVICE_PASSWORD` or
  `config\service.password`, or run **Complete bobiverse service logon** (Start Menu `Bobiverse` folder). LocalSystem + Admin-sealed
  `identity.json` -> `CryptUnprotectData failed` crash loop. Interim: park `identity.json` as `identity.json.admin-dpapi.bak`.
- NSSM must not bake `C:\Users\Default\.jeeves`; `Install-Jeeves` prefers the Admin chair home, else `home-jeeves`.
- `Start-Jeeves.ps1` launches `--chair --nick Jeeves --home .`; never pass an unquoted `#bobiverse` in a PowerShell command line
  (`#` starts a comment and drops the rest of the argv).

## Install, upgrade, rollback, hotpatch

See `bobiverse-fleet-ops`. Jeeves specifics: the installer also registers task `BobCallback`, runs `Install-BobWebhooks.ps1`
(IIS rewrite incl. public `/bob/v1/digest`), provisions the chair oper credential, and builds the single Start Menu folder
`Bobiverse` (Restart ircJeeves, Services, Logs, Skill books, Agent guide, Jeeves command reference - all with the systray icon).
Hotpatch = back up `<ai root>\jeeves`, copy changed `scripts\*`, `Restart-Service ircJeeves` ONLY.
**FR #3190:** do not re-enable retired task `BobAutoFocus` (ops `auto-focus.py` per-item `!focus` spam). Post-upgrade restarts `BobCallback` / `BobAutoFeed` only and runs `Unregister-BobAutoFocus.ps1`. Use repo-level `!focus <Owner/repo>`.

## Cutover checklist (Ergo host)

1. Remove SCM `BobJeeves`. 2. Ensure `config\ergo.password`. 3. `Complete-BobiverseServiceLogon.ps1 -Product jeeves` when the password is available.
4. `Restart-Service ircJeeves`. 5. Expect `joined #bobiverse,#... as Jeeves` and `chair-status ... op-in=` all channels.

## Do not

- Invent an Ergo PASS, stamp UAT, run `BobJeeves` and `ircJeeves` together, or restart `BobIrcd` to "fix" a chair problem.
- Print or commit `github.token`, `service.password`, `ergo.password`, `identity.json`, oper cred.

## Self-test / heal checks are extensible (FR #2522)

`jeeves.exe --self-test` runs the builtins (`imports`, `locks`, `http`, `queue`, `offer`; `health` on request) **plus** every `check_<name>.py` plugin found in `jeeves/checks` (bundled into the exe by `Build-Jeeves.ps1`; `JEEVES_CHECKS_DIR` overrides for tests). A plugin defines `CHECK_NAME` and `run(home, chair_home) -> (detail, findings, errors)`; `INCLUDE_IN_DEFAULT = False` makes it `--check <name>` only. Add/change checks and their pytest only via PR + MRB - never by editing the running exe.
