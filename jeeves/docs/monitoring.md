# Jeeves monitoring checks

## idle_seats (FR #1116)

`Test-JeevesMonitorIdleSeats.ps1` / `tools/monitor/idle_seats.py` finds idle digest seats only when at least one unaccepted row is **offerable** to a live idle seat (same gates as `offer_focus_top`: needs_human, cooldown, skip labels, machine pin, ledger, UAT/MRB rules).

- Gated-only queue + idle seats → EXIT 0
- Idle seats + offerable row → EXIT 1