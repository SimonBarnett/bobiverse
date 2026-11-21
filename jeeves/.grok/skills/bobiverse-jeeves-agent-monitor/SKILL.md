---
name: bobiverse-jeeves-agent-monitor
description: >
  Jeeves-agent health pass for the deterministic chair on walrus: service, IRC
  presence and +o, webhook/digest freshness, queue sanity, stuck offers/GIVEUP,
  chair-outbox and build-lock backlog. Read-only by default; says what to report
  vs escalate. Also the post-check that build and install skills call. Use for
  "is Jeeves healthy", post-install verify, stale digest, or /bobiverse-jeeves-agent-monitor.
depends_on: []
---

# bobiverse-jeeves-agent-monitor

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Distilled from how the Bob Grok Bot ran Jeeves queue/health checks (Oct-Nov 2026). Long-form loop and
per-check details stay in `bobiverse-jeeves-monitor` and `monitor-start`; this node is the short health
pass and the **post-check** for `bobiverse-jeeves-agent-build` and `bobiverse-jeeves-agent-install`.
Agent FRs: BOB-33..BOB-43 (#8678-#8688), J: skill root `J:\ai\jeeves\.grok\skills` (BOB-38 #8682, BOB-39 #8683).

## Rules

- **Read-only by default.** Observe, then report. No `!assign`, `!focus`, `!ignore`, queue/outbox edits,
  service restarts, `!recycle`, or installs from this skill. Those belong to the operator (Si) or Slab.
- Never touch Ergo (`BobIrcd`, `ircd.yaml`), AD/DNS/DHCP/SQL, or any process you did not start.
- Never read or print secrets: `config\*.password`, `github.token`, `identity.json`, oper cred, any
  `passwords` folder, `inbound-transcript.log`. Env dumps: show only non-secret lines (e.g. HOST/PORT).
- Times: convert UTC log stamps to the operator's zone before reporting; do not mix UTC and local
  (a past "70 min stuck" alarm was a UTC/BST mix-up).
- A remote/non-chair host cannot see chair-local files. Use the public digest; do not raise
  health/queue/stale-digest findings from a non-chair host (FR #8579 / #8651 class false alarms).

## Health pass (run in this order; stop at the first hard failure and report it)

1. **Token-free checks first.** On the chair host: `scripts\Invoke-JeevesMonitorCheck.ps1 -Check health`,
   then `stale_digest`, `queue_flow`, `giveup_loops`, `stuck_accepted`, `seats_stuck_doing`, `idle_seats`.
   Exit 0 ok / 1 finding / 2 error, one JSON line each. Prefer the JSON to reasoning.
2. **Service / process.** NSSM `ircJeeves` Running, one chair process only, uptime sane (not a crash loop:
   repeated restarts in `logs\stderr.log`). `BobCallback` may be a scheduled task; check `127.0.0.1:7700`
   is listening rather than `Get-Service`. Legacy `BobJeeves` must not exist (nick fight).
3. **IRC presence.** Jeeves in `#bobiverse` (and every registered shop), with `+o` in `#bobiverse`
   (`chair-status ... op-in=` lists all channels). Nick is exactly `Jeeves` (never `Jeeves_` / `Jeeves_l`;
   wrong-host or 433 must exit, FR #6947).
4. **Webhooks + digest.** `GET https://bob.ntsa.uk/bob/v1/report` returns 200 JSON, digest timestamp
   fresh (minutes, not hours), every online machine has a recent `lastSeen`, idle seats show empty `jobs`
   with `running=0`/`queued=0`. `webhook-health.json` has no open `down` target. IIS site rewrite to `:7700`
   intact (a 502/404 on `/bob/v1/report` = IIS/BobCallback, not the chair).
5. **Queue sanity.** `queue.json` parses; no accepted row older than the stuck sweep window (30 min, FR #5510)
   with a dead holder; no row GIVEUP-looping on the same seat; offerable rows exist while seats sit idle =
   finding. `!status` (ops) shows `github_resync:` ok and `github-api:` remaining > 0 with no 403s.
6. **Backlogs.** `chair-outbox.txt` drains (not growing between two looks a few minutes apart);
   chair `build-locks.json` has no lock older than the recipe max run (stale lock frees on next `!build`,
   FR #6491); `webhook-queue` not piling up.
7. **Version.** Installed `VERSION` / exe hash matches what the last install receipt says (see
   `bobiverse-jeeves-agent-install`). Unknown provenance is a finding, not a guess.

## Report vs escalate

| Situation | Action |
|---|---|
| All green | One short line (service, IRC +o, digest age, queue counts). Do not post to rooms. |
| Single finding with a script exit 1 | De-dup open issues, then intake FR/comment with the JSON as evidence. |
| Jeeves down, not in `#bobiverse`, lost `+o`, crash loop, digest stale > 30 min, webhooks DOWN | **Escalate to Si** in the DM with evidence. Do not restart or roll back from here; recovery is the install skill's ROLLBACK path and needs the operator's go. |
| Just after an install | Report PASS/FAIL per step above back to whoever ran the install; a FAIL is a rollback trigger. |
| Stuck seat / GIVEUP loop | Report only. Never `clear_seat_doing` a working seat (harvest #1967). |

## Verify

A health pass is complete only when steps 1-7 each have an observed value (not "probably ok") and the
report states the time (operator zone) it was taken.

## Stop rules

- Stop and escalate on any secret appearing in output; redact before quoting.
- Stop if a fix would need a write, restart or install: hand it to the operator / install skill.
- Do not repeat the same report or room post when nothing changed since the last pass.
