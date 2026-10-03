<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-digest-webhook/SKILL.md, last changed 2026-09-28. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-digest-webhook
description: >
  Fleet digest at https://irc.ntsa.uk/bob/v1/report: shape, who POSTs pcent,
  who consumes cursor_pools, and the accuracy checklist. Use when the user
  says digest webhook, reportUrl, pcent, cursor_pools, TipForm n/a,
  MarchHare Cursor, fingerprint, _digest-webhook-posted.json, or
  /bob-digest-webhook. Paint rules: bob-fleet-tray. Local meters: box-usage.
  Chair: bob-jeeves-chair. Fuel pick: bob-token-handoff. Do not invent
  usage numbers.
---

# Digest webhook

Code for the TipForm consume path is PR #306
(https://github.com/SimonBarnett/agentic_build/pull/306). This skill is the
recipe. Do not re-derive the URL or the group map.

## Endpoint

| | |
|---|---|
| URL | `https://irc.ntsa.uk/bob/v1/report` |
| Config | `config/bobiverse.json` `reportUrl` (same string) |
| GET | `Get-BobDigestUrl` (FR #354). Env: `AGENTIC_IRC_DIGEST_URL`, then `BOB_DIGEST_URL`. Else `config/bobiverse.json` `digestUrl` or `reportUrl`. Hard default: `https://irc.ntsa.uk/bob/v1/report`. Never `http://bob.ntsa.uk/bob/v1/digest` (does not resolve; IIS has no `/digest`). |
| POST | `Get-BobDigestReportUrl`: `reportUrl`, else `BOB_REPORT_URL`, else `AGENTIC_IRC_REPORT_URL`. |
| Auth | Header `X-Bob-Secret` from `BOB_REPORT_SECRET` or `~\.grok\bob\report.secret`. Never git, never the JSON body. |
| Verb | POST `op=merge` on a real peer delta (`Send-BobDigestWebhookIfChanged`). GET is read-only for TipForm / fuel. Do not HTTP GET as the publish path. |
| Git hook | `https://irc.ntsa.uk/bob/v1/git` is a different URL (`setup-github-webhooks`). Do not POST digest merges there. |

Cache: `Read-BobReportDigestHttp` holds the GET for 60 seconds.

## Who publishes

Every `bob-*` builder with a Cursor login runs `Write-BobIrcStatus` (**Watch-BobTray** and Watch-Bobiverse, **every 30s**) and **must POST `pcent`** plus **`overage_gbp`** (Cursor month overspend) and local xAI **`weekly`** when known. MarchHare has no Cursor login: it still POSTs local xAI weekly; it does not invent Cursor percents.

`Write-BobIrcStatus` builds `pcent` from `cursor_spending_groups` (PR #306):

| Local group id | `pcent` key |
|---|---|
| `auto` or `low-cost-models` | `cursor-models` |
| `high-cost-models` | `high-cost-models` |
| `grok-chat` | `grok-chat` |
| `sand_remaining_pct` | overwrites `grok-chat` |
| `on_demand_remaining_pct` | `on-demand` (not a TipForm bar) |

**#456 -- per-pool resets:** each Bob also POSTs slim `cursor_pools`
(`group_id`, `remaining_pct`, `period_end`) plus `sand_period_end`.
`grok-chat.period_end` / `sand_period_end` = Sand weekly reset;
`high-cost-models` / `auto` use Cursor `billingCycleEnd` (`cursor_period_end`).
Do not paint one reset clock on all three TipForm bars.

Fingerprint (`Get-BobDigestWebhookFingerprint`) includes the `pcent` JSON,
`cursor_pools` snapshot, `sand_period_end`, and `weekly` / `period_end`.
Merge payload (`Build-BobDigestWebhookMergePayload`) copies `weekly`,
`period_end`, `sand_period_end`, `pcent`, and `cursor_pools` through. A
weekly-only, pcent-only, or pool-reset-only change must POST.

**agentic_build #387 / gh-Jeeves:** the chair `op=merge` handler must **persist**
`machines.<id>.weekly` and `period_end` (xAI `Get-BobWeeklyRemaining`). If GET
digest shows workers but no weekly while local hover shows weekly remaining,
the chair was dropping those fields -- fixed in gh-Jeeves PR that lands
`coerce_machine` + merge for weekly/period_end. MarchHare may have empty
`pcent` (no Cursor login) and still must show weekly.

State file: `{IRC home}\bob-peers\_digest-webhook-posted.json` (`Get-BobDigestWebhookPostStatePath`). If that fingerprint equals the current doc, the next tick does not POST. **When the fingerprint blocks a needed republish** (pcent added in code but the state file predates it, or the chair is stale while the fingerprint still matches), delete `_digest-webhook-posted.json` and let the next `Write-BobIrcStatus` POST. Do not hand-edit the percent inside that file.

Hermetic capture (no live HTTP): `BOB_DIGEST_WEBHOOK_CAPTURE` = an ndjson path. Test-Pack uses it. Do not point it at a live box during a test.

## Who consumes

TipForm on every seat, including MarchHare:

- **CAST IRON (Simon 2026-09-27):** Cursor **pool check** (Agents start / fuel gate / "is there pool?") is **local Spending** (`Get-BobCursorAgentWeeklyRemaining`). Do **not** use digest GET / `cursor_pools` / `pcent` to decide pool remaining when local is known.
- GET the report URL for jobs, weekly tiles, and to **fill still-null** Cursor bars on hosts with no Cursor login (MarchHare).
- Digest must **not overwrite** a bar that local Spending or seat cache already set.
- Group aliases (`Normalize-BobCursorSpendingGroupId`, PR #306): `grok-weekly` / `grok_weekly` / `sand` / `grok-chat` -> `grok-chat`; `other-models` / `other_models` / `high-cost-models` -> `high-cost-models`; `cursor-models` / `low-cost-models` / `auto` / `on-demand` / `overage` -> `auto`.
- Also accept chair whisper `BOB DIGEST v1` (`Import-BobIrcTrayPull`) into `bob-peers\`.

Paint: `bob-fleet-tray`. Three bars only. No on-demand bar.

## Document shape (no sample numbers)

POST body (change-only merge):

```
op, machine, online, status
weekly, period_end, cursor_label, cursor_period_end
remaining_pct / account_remaining_pct / cursor_remaining_pct
overage_gbp (Cursor month overspend; omit when unknown)
pcent: { cursor-models, high-cost-models, grok-chat, on-demand }
running, queued, jobs[{repo, state}]
model, kind, repo, sha, fuel, working_on, responding
```

GET / chair digest (what TipForm reads):

```
v, ts, chairNick
cursor_pools[{ id, group|group_id, remaining|remaining_pct, period_end }]
machines.<id>.pcent
machines.<id>.task | jobs | weekly | running | queued | uptime_since
```

`pcent` values are remaining percent integers. Omit a key when unknown. Do not send `0` as a placeholder for unknown. `0` means exhausted.

## Accuracy checklist

Run this before trusting a bar or a fuel pick. Do not type a percent the JSON does not contain.

```
curl -fsS https://irc.ntsa.uk/bob/v1/report
```

1. HTTP 200 and JSON. If it fails, do not fall back to `http://bob.ntsa.uk/bob/v1/digest`.
2. `reportUrl` in `config/bobiverse.json` is exactly `https://irc.ntsa.uk/bob/v1/report`.
3. Each online builder that has a Cursor login has a `pcent` object. MarchHare may omit Cursor keys; that is not a license to invent them.
4. Keys you act on: `cursor-models` (auto / low cost models), `high-cost-models`, `grok-chat`. `on-demand` may be present and is not a bar.
5. `cursor_pools` rows must carry distinct `period_end` (grok-chat = Sand weekly / `sand_period_end`; high/auto = billing / `cursor_period_end`). Empty `cursor_pools: []` means peers cannot paint correct resets (issue #456).
6. `cursor_pools` group ids normalize as in the alias table above. Named seats stay per-seat; other pools fan out.
7. Body has no `password=`, `xai_api_key=`, `X-Bob-Secret`, `report.secret`, or `connect.password`.
8. `overage_gbp` may be null on the digest while local TipForm shows GBP. Prefer local `spendLimitUsage` / `Get-BobCursorOverageGbp` when that doc has `overage_gbp`. A label that is only `N%` is remaining, not overspend (overspend text starts with `-` or contains a GBP sign, `GBP`, or `$`).
9. Missing field -> `n/a` on the card and "no fuel number" for dispatch. Do not copy another seat's percent into a different spending group.

## Hard rules

- Do not invent usage numbers.
- Do not print the report secret.
- Builders POST. TipForm GETs. Jeeves whispers `BOB DIGEST v1` (chair), it is not a substitute for `pcent` on the webhook.
- Cursor pool remaining / Agents fuel gate: **local** Spending first. Digest fills nulls only.
- One home for fuel policy: `bob-token-handoff`.
