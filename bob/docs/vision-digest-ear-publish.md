# Vision: bobiverse digest ear-publish + TipForm fuel logos

Feature request on existing repo SimonBarnett/bobiverse. Reuses fleet **service** shape (ircBob + BobCallback); TipForm/Status is the UI delivery surface.

## Objective

Every fleet box publishes truthful, low-lag fuel (Cursor, xAI, OpenCode, Copilot) from the **bob-ear** service to `https://bob.ntsa.uk/bob/v1/report`, and TipForm/Status shows those pools with company logos and the real xAI account label - so operators never trust a week-old or nick-only digest again.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Ear-only fuel publish | Tray fuel POST removed/no-op; ear posts merges | Pins + grep Watch-BobTray / ear | Tray still POSTs fuel or ear silent |
| S2 | Report host default | Defaults resolve to https://bob.ntsa.uk/bob/v1/report | Assert + helper pins; GET 200 | irc-only default or wrong host |
| S3 | xAI account label | Known seats expose xAI/Grok account label != bob-<machine> | GET machines.<id> after tick | Missing, nick-only, or secret leaked |
| S4 | MarchHare pool truth | weekly/pcent/pool/reset match local meters within one publish cycle | Local meter vs GET | null/0% or stale reset with fresh lastSeen |
| S5 | No-lag on change | Remaining/OpenCode/Copilot delta visible on GET within 5s (or one pinned ear tick) | Fixture delta -> GET | Fingerprint suppress; multi-day stale fetched_at |
| S6 | OpenCode display | pcent.opencode-free/go plus Go rolling/weekly/monthly window lines on digest + TipForm when known | Fixture + UI | Absent/unknown/stale stay n/a; no invented reset |
| S7 | Copilot on systray | Status/TipForm Copilot line present and matches fresh digest | UI + GET copilot.fetched_at | Missing tile or multi-day fetch painted as current |
| S8 | Logo identity | Cursor, xAI/Grok, OpenCode, Copilot rows show correct logo or text fallback | Mocks + Status/TipForm | Wrong/missing logo with no fallback |

LOCKED

## Shape

Primary: **service**

Hybrid note: TipForm/Status/systray is the paint/delivery UI for the same digest document (ircBob ear publish + BobCallback merge); tray does not own fuel POST.

LOCKED
## Architecture

```
[Cursor Spending | xAI weekly + account label | OpenCode Get-BobOpencodeFuel | Copilot allowance]
        |
        v
  ircBob ear (on-change + tick) --POST op=merge--> https://bob.ntsa.uk/bob/v1/report
                                                         |
                                                    BobCallback / bobreport
                                                         |
  TipForm / Status / systray  <---- GET report -----------+
  paint: [logo] Cursor | [logo] xAI | [logo] OpenCode | [logo] Copilot
  (tray: no fuel POST)
```

Trust: no tokens/secrets in digest body; xAI account is a display label only. Local Cursor Spending remains Agents fuel-gate when known.

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | bob/docs/mocks/digest-fuel/home.html | primary fuel strip with logos |
| M2 | bob/docs/mocks/digest-fuel/empty.html | all unknown / n/a |
| M3 | bob/docs/mocks/digest-fuel/error.html | stale Copilot / publish fail / logo fallback |

## LOCKED

- Ear owns fuel publish; tray paints only
- Canonical report URL https://bob.ntsa.uk/bob/v1/report
- OpenCode ids opencode-free / opencode-go (from #6120/#6121)
- Copilot visible and fresh on systray/Status
- Company logos for all four fuel families
- Anti-omnibus small FRs; park with Refs not Closes

## UNKNOWN

- Exact on-disk source for xAI account label string per seat (Grok auth snapshot field name) - discover on origin/main during FR-003
- Exact ear tick interval if sub-5s on-change is impractical on LocalSystem - pin in FR-005 (must still beat multi-day lag)
- Final logo asset license/source files (must be redistributable; text fallback required)