# Jeeves monitoring checks

## empty-offer playbook (FR #2448)

When seats hear `nothing queued` while `queue.json` still has unaccepted rows, follow **[empty-offer-playbook.md](empty-offer-playbook.md)** (log fields `require_machine` / `ledger` / `out-of-focus`, seat-ledger heal once, shop workers on pin machines, link #2446). `queue_flow` raises a finding after **>10m** of pin-only empty offer for idle seats.

## idle_seats (FR #1116)

`Test-JeevesMonitorIdleSeats.ps1` / `tools/monitor/idle_seats.py` finds idle digest seats only when at least one unaccepted row is **offerable** to a live idle seat (same gates as `offer_focus_top`: needs_human, cooldown, skip labels, machine pin, ledger, UAT/MRB rules).

- Gated-only queue + idle seats → EXIT 0
- Idle seats + offerable row → EXIT 1
- Pin-only empty offer sustained >10m → EXIT 1 (`queue_flow`, FR #2448)