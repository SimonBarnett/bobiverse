---
name: bobiverse-jeeves-troubleshooting
description: >
  Debug playbook for Jeeves/chair problems - command denials, empty queue, +h grant loops, webhook down alerts, roster/ChanServ, BobCallback permissions, DPAPI, NSSM. Use when the Jeeves chair, a webhook, or the roster misbehaves.
---

# bobiverse-jeeves-troubleshooting

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

Start with `bobiverse-fleet-ops` (health checks, hotpatch rules, known-failure table). Jeeves-specific lessons:

| Symptom | Diagnosis / fix |
|---|---|
| Commands "do nothing" for the ear | The ear is only recognised as `bob-<machine>` for a machine on the roster. Check `!status roster:`; `!resync`; confirm the SASL account is logged in (`chan-privs` logs). |
| Operator: Jeeves "not responding" but shop still assigns | Service can be healthy and offering while the **operator nick** is stuck unverified (WHOIS / account not linked). Check `chan-privs` / chair logs for unverified WHOIS on that nick; `Restart-Service ircJeeves` to refresh account/priv state. Leave seats alone; **never** restart `BobIrcd`/Ergo (harvest #2179). Dual BobCallback / `DigestLockBusy` is a separate heal path. |
| Replies never arrive | Replies go by PM (not the channel). The chair logs `git-help pm nick=... kind=ear`; `cmd-trace.log` has the text. Rate limit: `!help`/`!list` 30 s per nick. |
| `!list` says "queue empty" but `!status` has unaccepted items | `!focus strict on` hides everything not focused. `!focus strict off` (and restore afterwards). |
| Operator: `nothing queued` / `bored empty` but queue.json is full | Strict focus + per-seat gates. Count in-focus unaccepted, then `offer_focus_top` per idle nick. Common blockers: self-MRB, same-machine `review_blocked`, `require_machine`, row+`seat-ledger.json` giveups, sticky `offered_to` with no ACK (harvest #2243 / #2309). |
| Cleared row `giveup_seats` but seat still empty | Also clear that seat under `seat-ledger.json` → `giveup` → `owner/repo#N`. After immediate ACK+GIVEUP, **stop** clearing — leave ledger and report the loop (harvest #2314). |
| Sibling seat empty while other-machine holds sticky MRB offer | Same-machine MRB block while another live machine exists is correct; unblock is ACK/recycle on the offered machine, not self-MRB (harvest #2309). |
| Operator: many open GitHub issues/PRs "not assigning" | Raw open counts are not the chair queue. Check `ungated_offerable` + shop `!bored` traces before claiming the chair is broken (harvest #1581). Monitor must not `!assign`. |
| `GRANT +h` repeated every 30-60 s | Not the chair: the ear is reconnecting. See the ear restart loop (missing `--host`). The chair caps at 3 grants/10 min then WARNs once; `removed by ChanServ` WARN = a ChanServ/AMODE fight. |
| `chanserv-sync timeout; keeping last good roster` | Two forced syncs overlapped or Ergo was slow; the last roster stays. Harmless once. |
| `ERROR chanserv LIST DENIED` | The Jeeves IRC oper lacks the `chanreg` capability (do not edit the Ergo config from here; tell the Ergo owner). |
| Webhook down alert in #bobiverse | `webhook-health.json` says which target/check. `local` down = `BobCallback` task not running (`schtasks /Run /TN BobCallback`, port 7700 free?). `public` down only = IIS site/ARR/rewrite (`Install-BobWebhooks.ps1`). |
| BobCallback cannot write the digest | The task runs as SYSTEM; the digest home must grant SYSTEM and the service user. Writes use unique `*.tmp` names and orphan cleanup; never delete `digest.json`. |
| BobCallback HTTP 000 / no `:7700` LISTEN | Prefer `schtasks /Run /TN BobCallback` when the task exists (FR #1831). Else one detached `Start-BobCallbackSupervised.ps1`. Wrapper **refuses** a second parent (FR #1767). Never stack task + second supervised. |
| `health` ok while report dead | Task `Ready`/`Running` alone is not healthy — require LISTEN + GET `/bob/v1/report` (or `/health`) HTTP 200. |
| `github_resync: no token` | Put the token in `config\github.token` (one line, ACL SYSTEM+Administrators). Handling is unchanged; only the source is logged. |
| Open PR disappeared from MRB queue after resync | Stale premature `mrb_done` purged the row. Open `pr_exists` must win; clear stale `mrb_done` like `fr_done` (FR #1585 / #1613 / PR #1606). |
| Many open PRs with no MRB unaccepted rows (resync blocked) | `git-claim.lock` timeout / OSError or `GitHub.token` 403 can drop issue+PR queue events while `gh pr list` still works (harvest #1927 / product #1811 → #1993). Heal: `enqueue_unaccepted(GitClaim MRB)` per open PR from `gh pr list`; `clear_seat_doing` for stale busy so `!bored` can offer. Prefer fixing the lock/token root; do not leave the queue empty of open PRs. |
| Chair keeps losing the nick `Jeeves` | Legacy `BobJeeves` (gh-Jeeves) still installed - remove it from the SCM. |
| `error: the following arguments are required: --channel` | An unquoted `#bobiverse` in a PowerShell command line. Quote it. |
| Mojibake / parse failure in a ps1 | Keep the BOM on existing ps1 files; write Python/JSON/outbox without BOM. |
| After MSI, service still runs old code | NSSM Application path - re-run `Install-Jeeves.ps1`; check `<ai root>\jeeves\VERSION`. |
| Ergo restarted when the MSI upgraded | `ergo.exe` hard link (#70) - verify `fsutil hardlink list <ai root>\ergo\ergo.exe` shows ONE name; the installer repairs it without stopping Ergo. |

## BobCallback heal (supervised single-owner; harvest #1465-#1651 / #1568 / FR #1767 / #1831)

Probe together: scheduled-task state, `:7700` LISTEN, and a fresh GET `http://127.0.0.1:7700/bob/v1/report`. Comment existing FRs `#1455` / `#1467` / `#1388` / `#1767` instead of twin intake when the class matches.

1. **HTTP 000 / no LISTEN** - count supervised parents first (`CommandLine` match `Start-BobCallbackSupervised.ps1`). If one already exists, do **not** Start-Process another — wait or `schtasks /Run /TN BobCallback` only. If none and the task is registered: **`schtasks /Run /TN BobCallback`** (FR #1831). If the task is missing: one **detached** `Start-Process` of `Start-BobCallbackSupervised.ps1`. The wrapper itself exits 0 when a second parent would start (FR #1767). Prefer supervised over bare `bobcallback.py`. Re-probe until HTTP 200.
2. **Never stack** - if task is `Running` while you start supervised, `Stop-ScheduledTask` first and prune extras until one supervised parent + one `bobcallback.py` child. Never run task + a second supervised together. Multi-supervisor digest.lock fights cause public INTAKE 502 (FR #1767).
3. **Stuck supervised, no python child** — task may show `Running` with HTTP 000 and no `bobcallback.py` child. Stop the task, kill the stuck supervised wrapper (exclude current `$PID`), then start one clean supervised.
4. **Exclude heal `$PID`** — when killing duplicate supervised/bobcallback processes, never match the heal shell itself (`CommandLine` match on `Start-BobCallbackSupervised` will suicide mid-flight).
5. **Do not kill the supervised parent** — `Start-BobCallbackSupervised` uses `Wait-Process`; killing that parent kills the `:7700` child. Always launch with `Start-Process` (detached/hidden). Never `&` the wrapper in an agent shell you may later stop.
6. **External kill / bare listener** — if the supervised wrapper vanishes with no exit WARN, suspect external `Stop-Process`. A bare `bobcallback.py` that stays HTTP 200 for 60s+ must be left alone; do not stack another supervised on top.
7. **Orphan python still serving** — after a heal, if only orphan `bobcallback.py` remains with HTTP 200, do not stack supervised; wait until report drops, then start one clean supervised.
8. **Brief timeout with LISTEN** — connect timeout while LISTEN is present: re-probe curl once with **--max-time >= 20** (harvest #2057 / FR #1993; 4s false-alarms under digest.lock); do not immediate restart. If the re-probe returns HTTP 200, leave the single supervised owner alone (harvest #1705/#1706).
9. **`digest.lock`** — leave a non-empty fresh lock alone when the holder PID is live (`bobcallback` or `irc_agent`). Clear only empty/stale foreign locks.
10. **`git-claim.lock` / `GIT fail err=queue*` (FR #1811)** — webhook enqueue failures are now `queue-lock-timeout` / `queue-read` / `queue-write` (not opaque `queue`). Claims spool to `git-claim-pending.jsonl` and drain on the next lock; raise wait via `BOB_GITCLAIM_LOCK_S` (default 30). Not the same bug as multi-supervisor BobCallback (#1767). Stuck 0-byte chair-held `git-claim.lock` still needs `Restart-Service ircJeeves` only (never BobIrcd).
11. **After heal** — `Invoke-BobiverseHarvest.ps1 -Flush` so intake queued during IIS/ARR 502 while `:7700` was down can drain.

Always finish with the harvest step (see rule above) - every row here was learned the hard way and is only useful if the next
agent files what it finds.
