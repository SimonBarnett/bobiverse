# Gap analysis — digest ear publish (vs origin/main a02e56a2)

Compared Success rows to modules on detached `origin/main` worktree `repo/` (2026-11-07).

| Success | origin/main state | Gap |
|--------|-------------------|-----|
| S1 Ear-only publish | Watch-BobTray calls Write-BobIrcStatus / Send-BobDigestWebhookIfChanged (~30s). Ear only post_digest_out_of_fuel | Move fuel merge into ircBob; tray POST off |
| S2 bob.ntsa.uk | Code hard-defaults already `https://bob.ntsa.uk/bob/v1/report` (Get-BobIrc, Watch-BobTray, bob_worker). Skills/docs often cite irc.ntsa.uk; live both 200 | Align config/docs/skills; Assert pins; no dual-SoT narrative |
| S3 xAI account | cursor_pools.account stamped as bob-<machine>; no distinct xAI label on digest | Add label field from local Grok auth snapshot (no secrets) |
| S4 MarchHare truth | Live: weekly=99, pcent/pools null, cursor_label 0%, resets 2026-11-07 vs peers 2026-11-14 | Fix merge/coercion/paint so weekly-known boxes do not publish false null/0%; reset from local meters |
| S5 No-lag | Change-only fingerprint + ~30s tray tick; Copilot fetched_at can sit days (live 2026-11-02) | On-change POST from ear; Copilot refresh on change/tick; lag pin <=5s |
| S6 OpenCode display | #6121: local fuel + bobreport retains opencode-free/go; Get-BobIrc/TipForm publish+paint have zero opencode hits | Ear posts pcent; TipForm/Status paint |
| S7 Copilot systray | report.copilot + Format-BobCopilotPoolLine exist; FR #4938 Status shows Copilot tile; live pool stale | Ear refreshes copilot; UI never paints multi-day fetch as current without stale mark |
| S8 Logos | No per-family company logos on fuel rows (Bob About uses ntsa-gut-logo only) | Assets + Status/TipForm/mocks for Cursor, xAI, OpenCode, Copilot |

## Non-gaps
- OpenCode seat/fuel math: already on main via PR #6121 / FR #6120 — do not re-implement.
- CAST IRON: local Cursor Spending remains fuel-gate SoT when known; digest fills nulls only.