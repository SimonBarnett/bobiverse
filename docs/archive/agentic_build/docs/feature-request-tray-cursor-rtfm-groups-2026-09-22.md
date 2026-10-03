<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-tray-cursor-rtfm-groups-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Bob tray Cursor bars by RTFM group (not one Models strip)

**Date:** 2026-09-22  
**Source:** Simon on `#bobiverse` (live tray feedback after #81 / #142 landed).  
**Repo:** `SimonBarnett/agentic_build` (tray / TipForm). Sister digest shape may need `agentic_irc` chair JSON later.

## Summary

The live `#Bobiverse` card still does **not** break Cursor spend down the way Cursor Billing / RTFM groups it. Simon: there should be at least **three** Cursor groups on the card:

1. **Grok chat** (or Cursor’s labelled chat / agent chat pool — use the RTFM name once confirmed)
2. **High cost models**
3. **Low cost models**

Also: seats are clearly online (talk agents on IRC), but the tray still fails to show that work as proper job lines in places — agents running must surface as task/job rows, not an empty/`no jobs` lie when the box is busy.

## Gap vs current tree

- `#91` (CLOSED) asked for **one bar per Cursor seat/account** (Smart Catalogue / Club Madeira / ntsa). That is necessary but **not sufficient**.
- `#142` / PR `#148` ingest `!bobiverse` JSON + merge-preserve peers. It does **not** define RTFM sub-groups under each seat.
- Skill `bob-fleet-tray` still documents one Models % per seat (`{seat} Models {N%}`), not chat vs high vs low.

## LOCKED

1. Do **not** gut the TipForm. Keep existing machine tiles, weekly bars, job lines, alerts.
2. Cursor section must show **>=3 group bars** matching Cursor RTFM / Spending breakdown (names may be normalised to ASCII labels once Billing strings are confirmed).
3. Per-seat bars from `#91` remain: groups nest **under** each seat (or clearly labelled per seat), not one house-wide strip that collapses seats again.
4. When this box or a peer has a live talk/build worker, the card must show a **non-empty job line** (repo/sha/model/description/runtime when known) — not `grok.exe ?` and not `no jobs` while IRC seats are active.
5. Refresh path stays `!bobiverse` / digest JSON (+ local meter), not POINT-only.

## UNKNOWN

- Exact Cursor Billing API / Spending field names for the three groups (confirm from live Spending UI / RTFM).
- Whether Grok Bot Sand is a fourth bar or stays the separate overage signal already on the card.
- Whether chair `_coerce_machine` / digest must grow new keys before the tray can paint groups, or local `Get-BobCursor*` can fill groups first.

## Acceptance (draft)

1. With live data on marchhare/flamingo, TipForm shows at least three Cursor group meters (chat / high-cost / low-cost) with remaining % or explicit `n/a`, without removing seat labels from `#91`.
2. While `marchhare-<seat>` / `flamingo-<seat>` (or a build worker) is online and working, that machine’s tile shows a real job line — not empty when the human can see the seat on IRC.
3. `tools/Test-Pack.ps1` locks fixture coverage for multi-group Cursor bars + non-empty job line when digest/task present.
4. Bob stamps UAT; hostile MRB on the implementer SHA.

## Related

- Closed: `SimonBarnett/agentic_build#91`, `#142`
- Skill: `.grok/skills/bob-fleet-tray/SKILL.md`
- Sister: `SimonBarnett/agentic_irc` digest / `#36` `!report` task lines
