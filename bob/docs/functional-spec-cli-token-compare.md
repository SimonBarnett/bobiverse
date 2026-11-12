# Functional spec: CLI token comparison

Pulled from the LOCKED sections of `bob/docs/vision-cli-token-compare-2026-11-12.md`.
Gap base `origin/main` `b429d9b1`.

## Objective

A finished Grok or Cursor CLI job records the same measured token fields OpenCode already records, those rows can be compared by model, and the Jeeves appliance status page draws that comparison.

## Behaviour

1. Grok. When `usage.json` has one `modelUsage` entry, the DONE stamp uses that entry's model id and its `inputTokens`, `outputTokens`, and `cachedReadTokens`. A different `primaryModelId` does not win. The ledger row stores the same numbers. Issue #6781.
2. Cursor. A non-zero local or fixture source stamps the same three fields and `model=`. A missing source, or token fields that are absent or zero, stamps `tokens=unknown`. Issue #6782.
3. Comparison. The ledger rollup groups measured rows by `model`. Unknown rows increment `unknown_jobs` and do not add into token sums. Issue #6783.
4. Status page. Inline SVG shows the rollup when measured rows exist. No measured rows: empty copy, no zero bars. Unreadable ledger: error copy, no invented series. Same auth as `/status`. Issue #6784. Mocks: `bob/docs/mocks/cli-token-compare/`.

## Fail

- Counts present in the Grok fixture and the stamp says `tokens=unknown`.
- A zero Cursor store becomes `tokens_in=0`.
- Two models land in one bucket, or unknown jobs count as zero tokens.
- `/status` has no token series, or an empty ledger draws a zero series.

## Out of scope

OpenCode sqlite changes, dollar cost, `costUsdTicks`, Cursor cloud export, pool-percent pages (#6759 and siblings), MSI, service restart, UAT, IRC.

## UNKNOWN

Cursor on-disk non-zero counts may not exist. Several Grok `modelUsage` entries in one session are not this spec.
