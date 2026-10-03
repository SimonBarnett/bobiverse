<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-bob-fleet-tray-all-machines-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build-and-test plan — tray all-machines peek (2026-09-19)

**FR:** docs/feature-request-bob-fleet-tray-all-machines-2026-09-19.md

## P0 — Registry
- Define canonical machine list (BobBridge `fleet/machines/*.json` + local machine.json).
- Ensure Install-BobFleet / heartbeat writes discoverable records on ionos, marchhare, ce-priority-dev1.

## P1 — Peer peek transport
- Choose one documented approach: shared folder under BobBridge home, or pull peer fleet JSON via existing connector path.
- Fail closed: tile shows unreachable/stale, never invent jobs.
- No Stop-ScheduledTask BobFleet-* while implementing.

## P2 — Hover UI
- Get-BobTrayHover builds tiles for **all** machines; jobs nested under each.
- Remove default “other hosts not in this store” when peers are registered.
- Keep weekly bar + Bob Fleet title + owner/repo labels.

## P3 — Tests + skills
- BT0 multi-host fixtures; update bob-fleet-tray skill.
- UAT notes from at least two boxes; hostile MRB to Bob.
