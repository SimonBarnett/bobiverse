---
name: Bob digest webhook fuel
description: >-
  Use when reading or fixing Bob Fleet fuel from the digest webhook
  (irc.ntsa.uk/bob/v1/report), TipForm n/a pools, missing machines.*.pcent,
  stale START job tiles, or choosing Grok-first (then Cursor) start-codes from live quota.
---
# Fleet digest webhook (fuel + activity source of truth)

## Endpoint
`GET`/`POST` `https://irc.ntsa.uk/bob/v1/report` (bobcallback).
Do **not** use `http://bob.ntsa.uk/bob/v1/digest` (404).
Env override: `AGENTIC_IRC_DIGEST_URL` / `BOB_DIGEST_URL`.
`config/bobiverse.json` `reportUrl` should match.

## Shape (v1)
- `cursor_pools[]`: fleet Cursor spending groups — `id` in `cursor-models`, `other-models`, `grok-weekly`, `on-demand`; field `remaining` is remaining %; `period_end`/`reset`.
- `machines.<id>`: per seat (`ionos`, `flamingo`, `marchhare`, `ce-priority-dev1`) with `nick`, `online`, `lastSeen`, `weekly`, `period_end`, `pcent`, `cursor_label`, **`jobs` / `running` / `queued` / `working_on`**.
- `machines.*.pcent`: map of group remaining % (prefer `grok-chat`, `high-cost-models`, `cursor-models`, `on-demand`). Alias normalize: `grok-weekly`/`sand` → grok-chat; `other-models` → high-cost-models; auto/low-cost → cursor-models/auto.

## Activity (jobs)
- TipForm seat lines come from digest tasks/jobs when present; idle must be **`no jobs`**.
- `running`/`queued` must match process-backed published `jobs` only. Empty `jobs` ⇒ both counts **0** (do not leave `running=1` from `@($null)` lane-read failures).
- Workers must report start and **clear** on finish — see [Bob worker activity webhook](sand-workflow:bob-worker-activity-webhook).
- Clear stale: remove ghost `fleet/inbox|running/<id>/*.json`, wipe fake rows in `_chair-digest-peers.json`, delete `_digest-webhook-posted.json`, run `Write-BobIrcStatus`.

## Publish path (each bob-*)
1. Ear runs `Write-BobIrcStatus` (Watch-Bobiverse / irc_agent).
2. Webhook merge payload **must include `pcent`** (fingerprint too) or digest stays empty for peers without Cursor login.
3. Clear `~/.agentic-irc-bobiverse/bob-peers/_digest-webhook-posted.json` (or chair home) if a stale fingerprint blocks re-post.
4. After code change: recycle **Watch-Bobiverse only** (CreateNoWindow; kill prior matching process first). Do not flap BobIrcd while orphan ergo holds :6697.

## Consume path (TipForm)
`Read-BobReportDigestHttp` → `Apply-BobIrcDigestCursorPools` fans pools to **all seats**. TipForm must accept **peer** `pcent`, not only `machine == local`. Cache: `cursor-pools.json` / seat-period-end under bob-bridge. Prefer digest jobs for tiles; never invent `irc agent` START from ear presence.

## Accuracy checklist before handoff
1. `curl -sS https://irc.ntsa.uk/bob/v1/report`
2. Every machine has fresh `lastSeen` and truthful `jobs`/`running`/`queued` (all zero when idle).
3. Fuel gate is **Grok first, then Cursor** (FR #3997: Grok refreshes weekly, Cursor monthly, so Cursor is the reserve). Start or restart a seat on **Grok** (agent.exe / grok start-codes) while this machine's xAI weekly Grok fuel is > 0. Use **Cursor** start-codes only when Grok is really exhausted on that machine (402 `usage balance exhausted`, `creditUsagePercent` 100, out-of-tokens dialog) AND Cursor Models has fuel. A failed or unknown read is NOT exhausted (#3923). Never switch a running seat mid-job. After the weekly Grok reset, the next start goes back to Grok. Note: digest `grok-weekly` is the Cursor Sand / Grok chat pool, not the machine's xAI weekly. Read Grok fuel from the machine (`Get-BobWeeklyRemaining`/`Get-BobGrokAvailability`). Never Copilot until CCA is live.
4. Do not invent %. If ntsa `unified.jsonl` period_end is pre-rollover, run the real billing fetch script — do not LLM-guess reset dates.

## Related
TipForm recycle: `_Watch-BobTray-<seat>.ps1` / kill all Watch-BobTray then one CreateNoWindow start.
Jeeves GIT chair: agentic_irc; `chairNick=Jeeves`; `BOB_DIGEST_HOME` = bobiverse home when `--home` is `.agentic-irc-jeeves`.
