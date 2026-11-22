---
name: bobiverse-jeeves-agent-fr-filing
description: >
  File an FR or issue the fleet way: twin-check first, one issue per issue
  (anti-omnibus), right repo (product repo vs bobiverse), feature-request
  label, evidence block, no secrets; close later twins with a reference to the
  first. Use before filing anything or /bobiverse-jeeves-agent-fr-filing.
depends_on: []
---

# bobiverse-jeeves-agent-fr-filing

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

## Steps

1. **Twin-check.** Search open (and recently closed) issues in the target repo for the same symptom and cause.
   If one exists, comment the new evidence there instead of filing.
2. **Right repo.** Product bugs go to the product repo (e.g. a-search for a-search code); fleet/Jeeves/worker
   issues go to `SimonBarnett/bobiverse`. Intake: `Report-BobiverseIntakeIssue.ps1 -Repo <owner/name>`.
3. **One issue per issue.** One root cause, one acceptance row. Split anything with "and also".
4. **Body:** what / where / evidence / fix. Evidence block = exact log lines, run ids, SHAs, timestamps with
   zone, and how to reproduce. Separate observed facts from guesses. Add `require_machine: <machine>` only
   when it truly must run there.
5. **Label** `feature-request` for FRs. Add `hold` only for parked/phase-gated work.
6. **Report** the URL. Do not assign or pin it yourself.

## Twins

When two issues cover the same thing, keep the **first**, close the later one with
"Duplicate of #<first>", and move any extra evidence to the first. Done issues are closed too.

## Never

Secrets, keys, tokens, oper creds, private IPs/hostnames, or `inbound-transcript.log` content in an issue.
Omnibus FRs. Filing the same thing twice because a search was too narrow.
