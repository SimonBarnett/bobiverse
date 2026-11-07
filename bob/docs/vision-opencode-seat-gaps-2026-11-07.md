# Vision: OpenCode bobiverse seat — remaining gaps

Feature request on existing repo SimonBarnett/bobiverse. Reuses fleet **service** shape (bob-worker + ircBob + TipForm).

## Objective

Fleet boxes can run OpenCode as a bob-worker seat (fuel-gated, shop IRC, outbox ACK/DONE) with truthful OpenCode fuel on the digest/TipForm, without false out-of-fuel kills or stale installs blocking selection.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Selection reaches OpenCode | After Grok+Cursor exhaust (or dry-run), decision=opencode when exe+fuel known | bob-worker --dry-run on rebuilt exe | never opencode with fuel+exe present |
| S2 | Shop job completes | One FR ACK→work→DONE without false out-of-fuel | worker.log + shop | watchdog pause mid-healthy run; done-miss loop |
| S3 | Digest shows pools | pcent.opencode-free / opencode-go on GET when local fuel known | #6146 + fixture | absent while local known |
| S4 | TipForm paints pools | Status/TipForm shows OpenCode lines | #6147 + UI | missing while digest has values |
| S5 | Install ships helpers | Sync/MSI includes fuel helper + skill; rebuilt worker contains opencode | pack/sync pins | live exe/helpers pre-#6120 after Sync claim |

LOCKED

## Shape

Primary: **service**

Hybrid note: TipForm/Status paints digest; bob-worker owns the OpenCode child; ircBob ear owns fuel merge publish (see digest-ear-publish vision).

LOCKED

## Stack

Windows fleet; OpenCode CLI (`opencode run`); PowerShell launch wrapper; `common/scripts/opencode_fuel.py`; existing Ergo shop wire. No new SaaS URLs or invented secrets.

LOCKED

## Architecture

```
opencode.exe + user auth.json (ACL)
        |
bob-worker select_agent: grok → cursor → opencode → dialog
        |
launch-opencode.ps1 → opencode run -m $BOB_OPENCODE_MODEL (per inject)
        |
shop #<machine> / outbox ACK|DONE|NACK|GIVEUP
        |
Get-BobOpencodeFuel → ear pcent merge → bob.ntsa.uk/report → TipForm
```

Chair gate FR #6134: kind=opencode skips MRB/UAT.

LOCKED

## Screens

No new product UI. Digest/TipForm mocks live under `bob/docs/mocks/digest-fuel/` (digest-ear-publish). OpenCode seat is console/headless.

## LOCKED

- Do not re-implement #6120/#6121/#6134 seat core
- Open digest paint FRs #6146 / #6147 (Refs, do not twin)
- Selection order grok → cursor → opencode → dialog
- Hostile MRB/UAT stay off OpenCode

## UNKNOWN

- Exact watchdog idle threshold / heartbeat marker format (pin in FR-OC-WATCHDOG)
- Exact turn_ended marker for OpenCode wrapper (pin in FR-OC-TURN)
- Plan-mode OpenCode usefulness (deferred)
