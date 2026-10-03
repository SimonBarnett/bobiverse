<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-digest-cursor-pools-cursor-only-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: digest cursor_pools = Cursor Spending groups only

**Date:** 2026-09-22
**Repo:** SimonBarnett/agentic_irc
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/130
**Raised:** Simon #bobiverse UAT (marchhare tray)

## Problem

TipForm / digest shows **Cursor** quotas labelled **Smart Catalogue / Club Madeira / ntsa**.
Simon: those are **xAI** accounts — not Cursor Spending pools.

## Official Cursor Spending (RTFM — not TipForm aliases)

https://cursor.com/help/models-and-usage/usage-limits — two **monthly** included pools:

1. **Cursor Models** (Grok 4.7/4.6/4.5, Composer 2.5)
2. **Other Models** (third-party)

https://cursor.com/help/grok-bot/plans — Grok Bot also has:

3. **Weekly usage** (included, weekly reset) — grok-chat / Sand pool
4. **On-demand** / Spending **Monthly Limit** (extra after weekly)

Legacy TipForm aliases (`grok chat` / `high cost models` / `low cost models`) map roughly to (3)/(2)/(1) but MUST NOT lock the wire to only those three names if Spending exposes more.

`config/bob-seats.json` maps machines → email seats (SC / Club Madeira / ntsa). That seat map is **xAI / Grok Build**, **not** a list of Cursor quota pool names. Do not paint those seat labels as Cursor pool rows.

## LOCKED

1. `cursor_pools` / Cursor section = real Cursor Spending group bars only (Cursor Models, Other Models, Grok Weekly, on-demand as documented).
2. Do **not** emit Smart Catalogue / Club Madeira / ntsa as Cursor quota entries.
3. Do not gut digest / TipForm. Sister TipForm consumer is agentic_build.
4. No UAT stamp.

## Related

- agentic_irc #81 (cursor_pools shape)
- agentic_build #151 / #152 (TipForm groups) — sister UI; Simon said this UAT complaint is **agentic_irc** wire
