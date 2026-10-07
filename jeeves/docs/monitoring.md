# Jeeves monitoring checks

## intake_allowlist (FR #3117)

`Test-JeevesMonitorIntakeAllowlist.ps1` / `tools/monitor/intake_allowlist.py` probes live `POST /bob/v1/intake` with do-not-file titles for known products (including `SimonBarnett/a-search` and `SimonBarnett/trutex`).

- HTTP **403** `repo_not_allowed` → EXIT 1 (live ircJeeves allow rule drifted; usually missing Sync/compose after an allow PR).
- Also asserts on-disk `common/scripts/intake.py` exposes `repo_allowed` / SimonBarnett owner gate (FR #3135) when the file is present.
- Remediation: confirm source allow rule, then on **ionos** run `Sync-BobiverseFromRepo` (or restart `ircJeeves` so start-time ff+compose picks up `main`).
- Overrides: `BOB_INTAKE_URL`, `BOB_INTAKE_REQUIRED_REPOS` (comma list), `BOB_INTAKE_PY`.

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