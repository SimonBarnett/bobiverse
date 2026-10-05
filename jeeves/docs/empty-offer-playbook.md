# Empty-offer operator playbook (FR #2448)

When shop seats hear **`nothing queued`** but `queue.json` still has unaccepted rows, the offer filter is usually correct. The backlog has shrunk to gates the live shop cannot take. Product root-cause / heal for ledger-suppressed pins: **#2446**.

## Where to look (CAST IRON short IRC line)

- **Channel:** always `<nick>: nothing queued` only (`format_nothing_queued`). Never a summary on IRC.
- **Chair log:** `INFO git-claim bored empty nick=…` plus `format_empty_offer_detail` fields:
  - `unaccepted` — rows still in the unaccepted bucket
  - `out-of-focus` — dropped by strict `!focus`
  - `require_machine` — blocked for this nick by machine pin
  - `offerable` — rows this nick could take (should be 0 when the short line fired)
  - `self_mrb` / `ledger` / `sticky` / `blocked_other` — per-nick gates
- Example log shape: `0 offerable for you under focus (3 unaccepted, 0 out-of-focus, 3 require_machine, ledger=1)`.

Also: `jeeves.exe --self-test --check offer` and monitor `queue_flow` JSON (`gated_counts`, `offerable_for_idle_seats`, notes).

## Operator checklist

1. **Read the log breakdown** for one idle nick (require_machine / ledger / out-of-focus). Do not assume the chair is broken.
2. **List unaccepted pins:** which `require_machine` values? Which repos?
3. **Shop workers on the pin machine:** digest `/report` `worker_list` for that machine. `running=1` with **0 shop workers** means DEV1/ce-priority pins will rot until a shop seat appears there.
4. **Seat-ledger giveup:** `~\.bobiverse\seat-ledger.json` → `giveup` → `owner/repo#N`. A living ionos pin (e.g. #1993) with every ionos seat ledger-suppressed looks like permanent empty. Clear **once** (row stamps + that seat's ledger entry) only when re-feeding is intentional; after immediate ACK→GIVEUP, **stop** clearing and file the loop (#2314).
5. **File unpinned work** so other idle machines get offerable FRs while pins wait (do not leave the fleet on pins-only).
6. **Focus:** outside-focus ungated rows will not offer under `!focus strict on` — expand focus or temporarily `!focus strict off` only as an operator choice.

## Monitor (FR #2448)

`tools/monitor/queue_flow.py`: when `unaccepted>0` and idle seats still see `offerable=0` with a require_machine-dominated backlog for **>10 minutes**, EXIT 1 with a `pin-only empty offer` finding (state file `monitor-empty-offer-starve.json` under the ops/chair home). Gated-empty under 10m stays EXIT 0 + notes.

## Related

- Living architecture pin / chair exe: #1993
- Incident root-cause FR: #2446
- Empty-offer log wording: FR #2309 / #2333; harvest #2243 / #2285 / #2309
