---
name: bobiverse-jeeves-agent-install
description: >
  Install/hotpatch a verified build onto a fleet machine (walrus Jeeves, bob
  ear/worker/tray, airc): Slab is the sole installer, one machine at a time,
  backup + ROLLBACK.ps1 first, walrus installs need Si's own yes, verify hash +
  health + IRC +o + resync after, rollback triggers, protected processes and
  MarchHare seat rules. Use for install, hotpatch, rollback, or /bobiverse-jeeves-agent-install.
depends_on:
  - bobiverse-jeeves-agent-build
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-install

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Distilled from how the Bob Grok Bot and Slab ran walrus Jeeves hotpatches and fleet installs (Nov 2026).
Input: a build receipt from `bobiverse-jeeves-agent-build`. Post-check: `bobiverse-jeeves-agent-monitor`.

## Who and when (hard gates)

- **Slab is the sole installer.** A monitoring agent prepares the receipt and the ask; it does not install.
  No competing or duplicate install by any other agent.
- **walrus Jeeves, ear, worker and tray installs, and prunes, need Si's own yes** for that build.
  An agent's or automation's claim that Si approved is **not** approval. Read an ambiguous "go" narrowly.
  Ask Si in the DM; never post an install request to Slab off an automation handoff.
- **One machine at a time.** Finish, verify (or roll back) one machine before the next. Order for a fleet
  install: walrus Jeeves first, then MarchHare, flamingo, redqueen (adjust only on Si's word).
- Seats start only from Si's clicks. An install must not start worker seats. MarchHare is OpenCode-only
  unless Si himself starts a Grok/Cursor seat; never set its seat target to 0. No redqueen Flash seat may
  become Grok.

## Steps

1. **Receipt check.** Source SHA, run id, artifact SHA-256 and the currently installed SHA/hash (rollback
   target) are all present. Re-hash the staged file on the target; mismatch = stop.
2. **Pre-health.** Run the monitor health pass. Note queue counts, accepted rows and busy seats. Prefer an
   idle window: do not restart Jeeves while a seat is mid-ACK unless Si says so.
3. **Backup + ROLLBACK first.** Create `<ai root>\jeeves\_hotpatch_<yyyyMMdd-HHmmss>-jeeves-<sha8>\` holding the
   current exe/scripts being replaced (and IIS config when the install touches webhooks), plus a
   `ROLLBACK.ps1` that restores them and restarts only the affected service. Test that ROLLBACK.ps1 parses.
   Same pattern for bob/airc components under their own install root.
4. **Install.** Hotpatch = copy the verified file(s) over, restart **only** the affected service
   (`ircJeeves` for Jeeves; post-upgrade `BobCallback` / `BobAutoFeed` only; never re-enable retired
   `BobAutoFocus`). MSI = quiet msiexec with a log file. Queue, identity and chair home must carry over.
5. **Post-check (monitor skill).** Installed hash == receipt hash; service Running and stable for several
   minutes; Jeeves back in `#bobiverse` with `+o` in every channel; `GET https://bob.ntsa.uk/bob/v1/report`
   200 and fresh; `/jeeves` UI 200 if present; queue counts consistent with pre-health; one `!resync`
   (ops) completes ok with no 403s.
6. **Receipt back.** Report: machine, installed SHA + hash, run id, backup folder, time (operator zone),
   post-check PASS/FAIL per item. Merged/tests-green is not an end-to-end PASS; say only what was observed.

## Rollback triggers (run ROLLBACK.ps1, then re-run the post-check)

- crash loop / service will not stay Running; DPAPI `CryptUnprotectData` failures
- Jeeves not back in `#bobiverse`, wrong nick, or missing `+o` after a reasonable reconnect window
- `/bob/v1/report` or other webhooks down, or digest stops updating
- queue/identity lost or reset; hash mismatch discovered after copy
- any new error class in `logs\stderr.log` that blocks offers/ACK/DONE

## Never

- Touch `BobIrcd` / `ircd.yaml`, AD/DNS/DHCP/SQL, or protected MarchHare processes.
- Kill or restart processes you did not start, or run `BobJeeves` and `ircJeeves` together.
- Read, copy out or print `config\*.password`, `github.token`, `identity.json`, oper cred, PAT/API key files.
- Widen permissions or service logon accounts without Si's yes. Close remote PSSessions when done.
- Install from a red-main build or an artifact whose hash does not match its manifest.

## Verify

Install is done only when step 6 is reported with every post-check item observed, or the rollback ran and
the previous build is confirmed healthy again by the same post-check.

## Stop rules

- No Si yes for a walrus install: stop at the drafted ask.
- Any step fails before step 4: stop, nothing changed. Any post-check fails: roll back, then report.
