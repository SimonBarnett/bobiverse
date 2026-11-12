# Functional spec: CLI token comparison

Pulled from the LOCKED sections of `bob/docs/vision-cli-token-compare-2026-11-12.md`.
Gap base `origin/main` `b429d9b1`.

## Objective

A finished Grok or Cursor CLI job records the same measured token fields OpenCode already records, those rows can be compared by model, and the Jeeves appliance status page draws that comparison. The appliance login page is https://bob.ntsa.uk/jeeves.

## Behaviour

1. Grok. When `usage.json` has one `modelUsage` entry, the DONE stamp uses that entry's model id and its `inputTokens`, `outputTokens`, and `cachedReadTokens`. A different `primaryModelId` does not win. The ledger row stores the same numbers. Issue #6781.
2. Cursor. A non-zero local or fixture source stamps the same three fields and `model=`. A missing source, or token fields that are absent or zero, stamps `tokens=unknown`. Issue #6782.
3. Comparison. The ledger rollup groups measured rows by `model`. Unknown rows increment `unknown_jobs` and do not add into token sums. Issue #6783.
4. Status page. Inline SVG shows the rollup when measured rows exist. No measured rows: empty copy, no zero bars. Unreadable ledger: error copy, no invented series. Same auth as `/status`. Issue #6784. Mocks: `bob/docs/mocks/cli-token-compare/`.
5. Login route. GET https://bob.ntsa.uk/jeeves returns the login HTML. A public GET is not a 403. `/bob/v1/*` is unchanged. Issue #6815. Mocks: `bob/docs/mocks/jeeves-login/`.
6. Butler graphic. The login page includes `jeeves/assets/jeeves-butler.ico`. No new character image. Issue #6816.
7. Home link. `jeeves/www/irc-ntsa/index.html` links to `/jeeves`. Issue #6818.
8. Sign-in. The form posts username, optional domain, and password to the existing session login. Passwords are not logged. Issue #6819.
9. Cookie. Settings and status still require the existing session cookie. Issue #6820.
10. Doc. `jeeves/docs/jeeves-settings-appliance.md` states https://bob.ntsa.uk/jeeves and no longer tells the operator to browse jeeves.ntsa.uk. Issue #6821. Bundle #6798 is closed.

## Fail

- Counts present in the Grok fixture and the stamp says `tokens=unknown`.
- A zero Cursor store becomes `tokens_in=0`.
- Two models land in one bucket, or unknown jobs count as zero tokens.
- `/status` has no token series, or an empty ledger draws a zero series.
- GET /jeeves is 403, the login page omits `jeeves-butler.ico`, or the Bob home page has no `/jeeves` link.

## Out of scope

OpenCode sqlite changes, dollar cost, `costUsdTicks`, Cursor cloud export, pool-percent pages (#6759 and siblings), a new DNS name, a new butler drawing, webhook route changes, reopening #6757, MSI, service restart, UAT, IRC.

## UNKNOWN

Cursor on-disk non-zero counts may not exist. Several Grok `modelUsage` entries in one session are not this spec.
