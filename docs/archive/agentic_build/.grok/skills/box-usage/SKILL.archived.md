<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/box-usage/SKILL.md, last changed 2026-09-28. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: box-usage
description: >
  Show Cursor Models remaining % (the MRB/PR fuel), Grok Build / Premium+
  (xAI), and Grok Bot / Cursor Sand on a Windows box: remaining %, reset
  dates, on-demand GBP overage, live grok processes, sessions, BobBridge
  jobs, and ~/.grok disk. Use when the user asks usage, quota, remaining,
  Cursor Models, reset date, overage, how maxed, Premium+ headroom, Cursor
  Sand, unpaid invoice, paid their bill, digest pcent, peer quota, or
  /box-usage. Fleet source of truth for peers is the digest webhook
  (bob-digest-webhook). Pair with cursor-sand-billing when Grok Bot is
  silent at Sand 100%. Pair with bob-fleet-tray for the TipForm card and
  grok-build-fleet when choosing ionos vs marchhare vs flamingo. Do not
  invent usage numbers.
---

# Box usage (this machine)

Run on the **target** Windows box via local-exec (ionos, flamingo, marchhare,
ce-priority-dev1). Do not guess another host's quota from chat.

**Peers:** the fleet source of truth is the digest webhook
`https://irc.ntsa.uk/bob/v1/report` (`bob-digest-webhook`), not a guess and
not MarchHare's local Cursor file (MarchHare has no Cursor login). Publish
path is `Write-BobIrcStatus`, which adds `pcent` from
`cursor_spending_groups` (PR #306). TipForm consumes that `pcent` and
`cursor_pools`.

## Digest curl (before you quote a peer percent)

```
curl -fsS https://irc.ntsa.uk/bob/v1/report
```

Checklist (detail in `bob-digest-webhook`):

- HTTP 200 JSON. URL is `reportUrl`, not `http://bob.ntsa.uk/bob/v1/digest`.
- Read `pcent.cursor-models`, `pcent.high-cost-models`, `pcent.grok-chat`. Missing key means unknown. Do not invent the number. `0` means exhausted.
- `overage_gbp` may be **null on the digest** while local TipForm shows GBP. Prefer local `spendLimitUsage` / `Get-BobCursorOverageGbp` when `overage_gbp` is present on the local doc. Do not treat a plain `N%` label as overspend.
- No secrets in the body (`password=`, `xai_api_key=`, `X-Bob-Secret`).

## One-shot report

```powershell
$repo = if (Test-Path 'C:\ai\agentic_build') { 'C:\ai\agentic_build' } elseif (Test-Path 'D:\ai\agentic_build') { 'D:\ai\agentic_build' } else { 'C:\src\agentic_build' }
Import-Module "$repo\src\BobBridge.psd1" -Force
# xAI / Grok Build weekly remaining + reset:
Get-BobWeeklyRemaining
# Cursor Models remaining (MRB/PR fuel) + Sand + GBP overage + reset:
Get-BobCursorAgentWeeklyRemaining
Get-BobCapacity | Select-Object -ExpandProperty cursor_models
# Full tray hover JSON (title, cursor row, machine tiles with seat + reset):
Get-BobTrayHover | ConvertTo-Json -Depth 6
# Or:
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\tools\Get-BobBoxUsage.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\tools\Get-BobBoxUsage.ps1" -Hover
```

Never paste `auth.json`, sand-secrets, or bearer tokens.

## xAI / Grok Build (per seat)

| Signal | How |
|---|---|
| Weekly remaining % | `Get-BobWeeklyRemaining` from last `billing: fetched credits config` in `~\.grok\logs\unified.jsonl`. Legacy ≤1.0.40: `100 - creditUsagePercent`. Grok 1.0.41+: no `creditUsagePercent` — `remaining_pct`/`used_pct` stay `$null` (`n/a`); still return `period_end` (FR #427). Period type must match WEEKLY / `USAGE_PERIOD_TYPE_WEEKLY`. |
| Availability (start gate) | `Get-BobGrokAvailability` (FR #430): `available` / `exhausted` / `unknown` / `auth-failed` / `stale`. Null % + local `allow_access` + current `period_end` ⇒ `available` (no API key). Only `remaining_pct=0` is exhausted. Never invent %. |
| Reset date | Same doc -> `period_end` (`currentPeriod.end`). Format for UI: `Format-BobResetLabel` -> `Until reset: …` / `reset DD Mon` (UK local). Shown even when weekly % is `n/a`. Display-only — not an eligibility proof. |
| Seat map | `config/bob-seats.json`: ionos=Smart Catalogue, flamingo=Club Madeira, marchhare+ce-priority-dev1=ntsa (si@ntsa.uk). Same seat -> one shared remaining % (min) and one shared reset |
| Publish to fleet | `Write-BobIrcStatus` writes `weekly` + `period_end`, POINT `reset=YYYY-MM-DD`, and digest `pcent` (POST `reportUrl`) |

## Cursor dashboard meters (do not mix)

Spending (`cursor.com/dashboard/spending`) included meters on the TipForm
(Simon labels; API in `tools/Get-CursorAgentUsage.py`):

| TipForm group | Spending / API source | Fuel |
|---|---|---|
| **grok chat** | `GetSandUsageStatus.usagePercent` -> `cursor_spending_groups[id=grok-chat]` | `grok-bot` only (Sand). Not MRB/PR fuel. |
| **high cost models** | `GetCurrentPeriodUsage.planUsage.apiPercentUsed` | named / Other Models |
| **Low cost models** (id `auto`) | `planUsage.autoPercentUsed` (Auto picker / `autoBucketModels`) | `cursor-models` for MRB and PRs |

**Low cost models** (wire id `auto`) is the pool when the model is Auto -- not
on-demand. Docs: Auto bills at the routed model's list price from **Cursor
Models** (and Other Models if the router picks third-party). Do **not** paint
an on-demand usage bar; header `overspend GBP...` (USD cents -> GBP,
right-aligned in the tile host) covers spend-limit pay-as-you-go.

TipForm paints **three labelled bars**. Hover JSON: `cursor_pools` (three
rows). Wire id stays `auto`; TipForm label is **Low cost models** (FR #448).
Cursor Models ~ auto.

| Signal | How |
|---|---|
| Low cost models remaining % | Must match Spending `autoPercentUsed` (100 - used). `Get-BobCapacity.cursor_models.remaining_pct`. |
| grok chat remaining % | Sand `usagePercent` via `cursor_spending_groups` / `sand_remaining_pct`. |
| high cost models remaining % | `apiPercentUsed` via `cursor_spending_groups`. |
| Empty / overspent GBP | `overage_gbp` from `spendLimitUsage.individualUsed` -- header only, not a bar. Digest `overage_gbp` may be null; prefer this local value when present. |
| Reset date | **Every** spending group row: `reset DD Mon`. `grok chat` -> Sand `sand_period_end` only (never Cursor `billingCycleEnd`, FR #448); high/Low cost models -> `billingCycleEnd`. |
| Cache | `~\.grok\bob-bridge\cursor-agent-usage.json` (~15 min); delete to force refresh |

## TipForm wiring

`Get-BobTrayHover` sets `reset_label` on **each** of the three `cursor_pools`
rows, plus each machine tile. Overspend is right-aligned inside the tile host
(host width - text - 2px). Agent section icons resolve Desktop `.lnk` then
Program Files `Grok Bot` / Cursor exe (`ExtractAssociatedIcon` plated on a
light chip).

## Other signals

| Signal | Source |
|---|---|
| Subscription display (e.g. X Premium+) | `~\.grok\settings_cache.json` -> `settings.subscription_tier_display` |
| Live `grok.exe` | `Get-Process grok` / `Get-BobLiveGrokAgents` |
| BobBridge lanes | `Get-BobBuilds` when available |
| GitHub issue post ready | `Get-BobHealth.gh_posting` / `Get-BobGhPostingReadiness` |
| Disk under `~\.grok` | `grok du --json` |

## Hard rules

- Do not invent weekly % or reset dates.
- Do not print tokens or auth.json.
- DEV1 must not use `XAI_API_KEY` (OIDC session, same ntsa seat as marchhare).
- Peer Cursor pools come from digest `pcent` / `cursor_pools`. Local `Get-BobCursorAgentWeeklyRemaining` is for a host that has a Cursor login.

### TipForm pools / countdown (FR #445 / #448)

- **grok chat** bar = Cursor Sand only (`sand_remaining_pct` / `cursor_spending_groups[id=grok-chat]`). Never copy auto / high-cost.
- **grok chat** reset = Sand weekly (`sand_period_end`) only — never Cursor `billingCycleEnd` / `period_end` (FR #448).
- TipForm label for wire id `auto` is **Low cost models** (id stays `auto`).
- Reset countdown has **no** `Until reset:` prefix. `days > 0` → `N days, M hours`; `days = 0` → `N hours, M minutes`.
- Local Bob publishes only its own pools (`Get-BobCursorPoolsForTray -LocalOnly` on Write-BobIrcStatus).

