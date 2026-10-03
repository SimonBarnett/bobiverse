<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-fleet-tray-good-systray-vs-dark-card-2026-09-19.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Bob Fleet — stop the dark hover card covering the good systray tip

**Date:** 2026-09-19  
**Repo:** https://github.com/SimonBarnett/agentic_build  
**Raised by:** Simon (via Bob)  
**Evidence:** `docs/screenshots/bob-fleet-tray-crap-card-over-good-tip-1.png`, `...-2.png`

## Problem (Simon)

There are **two** tray UIs:

1. **Good systray** — compact native/notify tip near the clock (e.g. `P+ idle 48%`). Works well when alone.
2. **Crap one** — large dark **Bob Fleet** hover/popup card (weekly remaining bar + machine tiles) parked over the notification area.

The large card sits **on top of / hides** the good tip. When the crap card hides/dismisses, the good tip works correctly again.

Simon: *"the good systray is hidden behind a crap one; when the crap one hides it work well"*

## Ask

Fix layering / ownership so the **good** systray tip remains usable:

- Prefer **one** primary hover surface: either improve the native tip **or** the dark card — not both fighting for the same corner.
- If the dark Bob Fleet card stays: it must **not** permanently obscure the notify-icon tip / clock tray; dismiss on mouse-leave, click-outside, or Escape; never steal the tray icon’s own tooltip forever.
- If the native tip is the “good” one Simon wants day-to-day: make the dark card **opt-in** (e.g. click tray icon once for fleet detail) rather than auto-hover covering the tip.
- Keep weekly-limit remaining % and all-machines nested jobs (FR `docs/feature-request-bob-fleet-tray-all-machines-2026-09-19.md`) — this FR is about **UX conflict**, not removing fleet data.

## Likely touch points

- `tools/Watch-BobTray.ps1`
- `src/Public/Get-BobTrayHover.ps1`
- prior NC dark-card / park-once / follow-cursor fixes (`e50ce69`, `fc3e61b`, etc.)

## Acceptance

1. With tray running, hovering the Bob Fleet notify icon does **not** leave a large card stuck over the system clock / “good” tip.
2. The compact weekly % indicator (good tip or equivalent) remains readable without dismissing a blocking card first.
3. Full fleet detail (machines + nested jobs + weekly bar) still available via an intentional gesture (click or short hotkey), not a sticky overlay.
4. UAT screenshots before/after; hostile MRB; recycle Watch-BobTray on ionos (and other hosts if applicable).
5. Commit/push to main.

## Out of scope

- Changing weekly quota math
- agentic_fomprep / Priority catalog renames
