# Jeeves monitoring checks

## empty-offer playbook (FR #2448 / #2446)

When seats hear `nothing queued` while `queue.json` still has unaccepted rows:

- Operator playbooks: **[empty-offer-playbook.md](empty-offer-playbook.md)** (FR #2448) and **[empty-offer-operator.md](empty-offer-operator.md)** (FR #2446 heal APIs).
- Log fields: `require_machine` / `ledger` / `out-of-focus`; seat-ledger heal when every live pin-machine seat GIVEUP'd; shop workers on pin machines.
- `queue_flow` auto-heals pin+ledger starvation (FR #2446) and raises a finding after **>10m** of pin-only / empty offerable for idle seats (FR #2448).

## idle_seats (FR #1116)

`Test-JeevesMonitorIdleSeats.ps1` / `tools/monitor/idle_seats.py` finds idle digest seats only when at least one unaccepted row is **offerable** to a live idle seat (same gates as `offer_focus_top`: needs_human, cooldown, skip labels, machine pin, ledger, UAT/MRB rules).

- Gated-only queue + idle seats → EXIT 0
- Idle seats + offerable row → EXIT 1
- Pin-only empty offer sustained >10m → EXIT 1 (`queue_flow`, FR #2448 / #2446)