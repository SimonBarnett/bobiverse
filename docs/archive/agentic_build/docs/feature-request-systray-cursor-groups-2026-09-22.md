<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-systray-cursor-groups-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: systray Cursor usage broken down by group

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/151
**Raised by:** Simon on #bobiverse (flamingo-17568 wake)
**UAT + hostile MRB owner:** Bob
**Skills:** bob-fleet-tray, box-usage

## Problem

Simon: **bob tray is still not broken down by group**. There should be
**grok chat**, **high cost models**, **low cost models**. There are **at
least 3 groups** for Cursor — RTFM the Spending dashboard.

Today TipForm paints one **Cursor Models (N%)** bar per *account seat*
(Smart Catalogue / Club Madeira / ntsa). That is seat-split (#91), not
Cursor *usage-group* split. One blob per seat is still wrong.

## LOCKED

1. Card must show **at least three Cursor groups** with Simon's names:
   **grok chat**, **high cost models**, **low cost models**.
2. Do **not** collapse those into a single Cursor Models bar.
3. Do **not** gut the card. Machine tiles, seat weekly bars, jobs_text,
   digest ingest (#142 / #148 / MRB #150) stay.
4. Numbers come from Cursor Spending (RTFM). Do not invent remaining %.
5. No UAT stamp. No secrets in git or goals.
6. Additive UI only.
7. **Agents that are on IRC are running.** Simon (same wake): *and there
   definitely are agents running because you're all here*. The card must
   list live `bob-*` and talk seats (`{machine}-{seatPid}`) from NAMES /
   digest workers — not `no jobs` / offline while those nicks are in
   `#bobiverse`.

## UNKNOWN (do not invent)

- Exact dashboard / API field names for the three groups (map after RTFM).
- Which group is the MRB/PR fuel gate (cursor-models picker). Until
  known, do not silently reuse one group as the old single Cursor Models %.
- Whether Grok Bot Sand / Other Models remain extra rows (old box-usage
  table) vs folded into these three.

## Gap vs tree

| Current | Wanted |
|---|---|
| One Cursor Models % per seat | >=3 group bars (grok chat / high cost / low cost) |
| box-usage: Cursor Models + Other Models + Grok Bot Sand | Align to Simon's three groups after RTFM |
| cursor_pools is per seat, one remaining_pct | Per seat, per group (or equivalent hover fields) |
| Watch-BobTray arCaption one account row | Group rows; keep machine tiles |

## Acceptance

- Hermetic Test-Pack: fixture with three group remainings paints three
  labelled bars; no live billing HTTP.
- Hover JSON exposes the groups; tray does not show a single merged
  Cursor Models % as the only Cursor row.
- Existing machine tiles still render.
- Skills ob-fleet-tray + ox-usage name the three groups.
