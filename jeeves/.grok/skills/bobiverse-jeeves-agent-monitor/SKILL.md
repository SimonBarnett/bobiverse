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
Agent FRs: BOB-33..BOB-43 (#8678-#8688), J: skill root `J:\.grok\skills` (BOB-38 #8682, BOB-39 #8683; J: is the walrus share `Jeeves` = `C:\ai\jeeves`).

## Where things are (walrus, the Ergo machine; checked 21 Nov 2026)

| What | Path / value |
|---|---|
| Jeeves install root (SMB share `Jeeves`, mapped as `J:`) | `C:\ai\jeeves` = `\\walrus\Jeeves` = `J:\` |
| Skill DAG root served to the Jeeves agent | `J:\.grok\skills` (= `C:\ai\jeeves\.grok\skills`); source of truth `jeeves/.grok/skills/` in SimonBarnett/bobiverse, laid by `Install-Jeeves.ps1` |
| Chair exe | `C:\ai\jeeves\jeeves\jeeves.exe` (+ `jeeves.exe.sha256`, `MANIFEST.json`, `provenance.txt` beside it) |
| Services | NSSM `ircJeeves` (the chair). Ergo is `ErgoWalrus` on walrus (`BobIrcd` on generic `Install-BobIrcd.ps1` hosts) |
| Service logs | `C:\ai\jeeves\logs\stdout.log`, `stderr.log` (no timestamps) |
| Chair home | `C:\Users\Administrator\.jeeves` (`cmd-trace.log`, `webhook-health.json`, `build-locks.json`, `stall-filer.json`) |
| Digest home | `C:\Users\Administrator\.bobiverse` (`digest.json`, `builds-catalog.json`, `mrb-reviewer-deadlock.json`) |
| Local webhook | `http://127.0.0.1:7700` (`/health`, `/bob/v1/report`, `/bob/v1/builds`) |
| Public webhook | IIS site `irc-ntsa` binds `bob.ntsa.uk` and `irc.ntsa.uk`; rewrite rules `BobReportWebhook`, `BobDigestWebhook`, `BobBuildsWebhook`, ... -> `:7700`. Use `https://bob.ntsa.uk/bob/v1/report` and `/bob/v1/builds` from off the LAN (`irc.ntsa.uk` answers on the LAN but may time out from outside) |

Remote checks run from the operator host (redqueen) over PSRemoting; always close the session:

```powershell
$s = New-PSSession -ComputerName walrus -ErrorAction Stop
try { Invoke-Command -Session $s -ScriptBlock { <# read-only checks #> } }
finally { Remove-PSSession $s }
```

If the session cannot be opened (Test-WSMan / PSSession error), see `bobiverse-jeeves-agent-winrm`; report
the machine as unreachable rather than guessing its state.

## Rules

- **Read-only by default.** Observe, then report. No `!assign`, `!focus`, `!ignore`, queue/outbox edits,
  service restarts, `!recycle`, or installs from this skill. Those belong to the operator (Si) or Slab.
- Never touch Ergo (`ErgoWalrus` on walrus, `BobIrcd` elsewhere, `ircd.yaml`), AD/DNS/DHCP/SQL, or any process you did not start.
  Restarting `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- Never edit `queue.json`, the Jeeves ledger, outbox or digest by hand. Never send a fake `ACK`, `DONE`, `!bored`
  or `GIVEUP`; never `!assign`; never `!build cancel`.
- Never open `inbound-transcript.log`, NSSM env values, `config\oper.cred` or `_backup-nssm-env-*`; listing names and sizes is fine.
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
2. **Service + /health.** `(Invoke-WebRequest http://127.0.0.1:7700/health -UseBasicParsing).Content` returns
   `"ok":true`, `"digest_writable":true`; note `pid`, `lock_pid`, `lock_own`, `lock_break_count`. A 503 with
   `lock_own` true is the FR #2902 class (own live lock), not a dead chair. NSSM `ircJeeves` Running, one chair process only, uptime sane (not a crash loop:
   repeated restarts in `logs\stderr.log`). `BobCallback` may be a scheduled task; check `127.0.0.1:7700`
   is listening rather than `Get-Service`. Legacy `BobJeeves` must not exist (nick fight).
3. **IRC presence.** `logs\stdout.log` has recent
   `INFO channel-sync registered=5 joined=#bobiverse,#redqueen,#marchhare,#flamingo,#wonderland` (order varies; every
   registered `#{machine}` plus `#bobiverse` must be listed). If `stdout.log` LastWriteTime stops at the last service
   start while `/health` stays fresh, use `cmd-trace.log` (chair home) for timed evidence and file it; do not read NSSM
   env to find the log. Jeeves in `#bobiverse` (and every registered shop), with `+o` in `#bobiverse`
   (`chair-status ... op-in=` lists all channels). Nick is exactly `Jeeves` (never `Jeeves_` / `Jeeves_l`;
   wrong-host or 433 must exit, FR #6947).
4. **Webhooks + digest.** `/health` `last_digest_write` within minutes of now and `digest.json` (digest home)
   LastWriteTime agrees; `GET https://bob.ntsa.uk/bob/v1/report` returns 200 JSON with `"stale":false`, `stale_age_s` small, every online machine has a recent `lastSeen`, idle seats show empty `jobs`
   with `running=0`/`queued=0`. `webhook-health.json` has no open `down` target. IIS site rewrite to `:7700`
   intact (a 502/404 on `/bob/v1/report` = IIS/BobCallback, not the chair).
5. **Queue sanity.** `queue.json` parses; no accepted row older than the stuck sweep window (30 min, FR #5510)
   with a dead holder; no row GIVEUP-looping on the same seat; offerable rows exist while seats sit idle =
   finding. `!status` (ops) shows `github_resync:` ok and `github-api:` remaining > 0 with no 403s.
6. **Builds catalog route.** `GET http://127.0.0.1:7700/bob/v1/builds` and `https://bob.ntsa.uk/bob/v1/builds`
   (IIS rule `BobBuildsWebhook`) both return the JSON array from `builds-catalog.json` (digest home). Public empty but
   `:7700` not = IIS rule missing; both empty = file missing or invalid. Jeeves reads the URL and does not fall back to
   the local file, so a missing route shows as an empty `!build` list.
7. **Build locks + backlogs.** Chair `C:\Users\Administrator\.jeeves\build-locks.json` (`{"builds": {}}` = no build
   running); recipe machines also use `C:\ProgramData\Bobiverse\build-locks.json` (FR #5266). An entry older than the
   recipe max run is stale (frees on next `!build`, FR #6491): report it, never delete it. `chair-outbox.txt` drains
   (not growing between two looks a few minutes apart); `webhook-queue` not piling up.
8. **Version.** `& C:\ai\jeeves\jeeves\jeeves.exe --version` prints the full commit sha; it must equal
   `provenance.txt` `source_commit`, the exe hash must equal its `exe_sha256`, and both must match the newest
   `_hotpatch_*-jeeves-<sha8>` folder (see `bobiverse-jeeves-agent-install`). Unknown provenance is a finding, not a guess.

## Known failure patterns

| Pattern | What you see | Action |
|---|---|---|
| Mid-turn assign / done-miss (#8738) | Chair offers the next job to a seat whose last ACKed job has no DONE yet; seat GIVEUPs or the earlier job is lost | Report seat, both issue numbers and cmd-trace times; comment on #8738, do not twin |
| Stale START tiles | Digest/TipForm shows a START job on an idle seat (`running=0`, no process) | Report; the worker must clear its own activity. Never edit the digest |
| Self-review deadlock | `mrb-reviewer-deadlock.json` fresh, MRB offered only to the author seat | Report (FR #5164 / #6256 class) |
| Empty `!build` list | Bare `!build` shows nothing | Step 6: route or `builds-catalog.json` missing |
| Red main blocks installs | `build-jeeves` failing on main HEAD | See `bobiverse-jeeves-agent-build` (last green commit only) |

## Report vs escalate

| Situation | Action |
|---|---|
| All green | One short line (service, IRC +o, digest age, queue counts). Do not post to rooms. |
| Single finding with a script exit 1 | De-dup open issues, then intake FR/comment with the JSON as evidence. |
| Jeeves down, not in `#bobiverse`, lost `+o`, crash loop, digest stale > 30 min, webhooks DOWN | **Escalate to Si** in the DM with evidence. Do not restart or roll back from here; recovery is the install skill's ROLLBACK path and needs the operator's go. |
| Just after an install | Report PASS/FAIL per step above back to whoever ran the install; a FAIL is a rollback trigger. |
| Stuck seat / GIVEUP loop | Report only. Never `clear_seat_doing` a working seat (harvest #1967). |

## Verify

A health pass is complete only when steps 1-8 each have an observed value (not "probably ok") and the
report states the time (operator zone) it was taken.

## Stop rules

- Stop and escalate on any secret appearing in output; redact before quoting.
- Stop if a fix would need a write, restart or install: hand it to the operator / install skill.
- Do not repeat the same report or room post when nothing changed since the last pass.
