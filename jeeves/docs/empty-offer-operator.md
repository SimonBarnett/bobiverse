# Empty offer / require_machine pin starvation (FR #2446)

Seats may hear `nothing queued` on the shop while `queue.json` still has **unaccepted** rows. The IRC line stays short on purpose (CAST IRON). The **chair log** carries the breakdown:

```text
{nick}: 0 offerable for you under focus ({U} unaccepted, {F} out-of-focus, {R} require_machine, ledger={L}, ...)
```

Built by `gitclaim.summarize_empty_offer` / `format_empty_offer_detail` (shop reply stays `format_nothing_queued` → `{nick}: nothing queued`).

## When only require_machine pins remain

Typical pattern (incident 2026-10-05):

1. Focused repos have few open FRs; resync leaves only **machine-pinned** rows (`require_machine=ionos`, `ce-priority-dev1`, …).
2. Pin machine seats **GIVEUP** the living FR → durable **seat-ledger** `giveup` blocks those nicks forever.
3. Other fleet machines cannot take the pin; pin machine has no willing seat → every `!bored` looks empty.

## Operator path (heal)

1. Read chair log empty-offer lines: confirm `require_machine` and `ledger` counts (not a blank unexplained empty).
2. Inspect seat-ledger giveup for the pin key (`owner/repo#N`) under the chair home (`.bobiverse` backup if you snapshot first).
3. Confirm digest `/report`: pin machine has **shop workers** (`worker_list`), not only `running=1` ghosts.
4. Heal options:
   - Prefer monitor auto-heal: `queue_flow` clears ledger giveup when **every live seat on the pin machine** has GIVEUP'd that pin FR (`heal_require_machine_all_gave_up`).
   - **Exception (FR #2486):** Living FR / Refs-only tracking umbrellas (body cue `Living FR` / `Refs-only` / `keep appending`, or labels `living` / `refs-only` / `tracking-umbrella`) are **excluded** from auto-heal so operator GIVEUPs stick (e.g. bobiverse#1993). Clear those giveups only with an explicit manual `ledger_clear_giveup` when you intend to re-offer.
   - Manual: `gitclaim.ledger_clear_giveup(home, repo, ident, nick=None, task="FR")` (omit nick to clear all), or edit ledger carefully.
5. File **unpinned** follow-up FRs so marchhare/flamingo stay fed while pins wait for the right box.
6. If pin machine has **zero** shop seats, start workers there (or clear/adjust the pin) — see monitor note `require_machine pins only; no seats on …`.

## Monitor (FR #2446)

`jeeves/tools/monitor/queue_flow.py`:

- **Heal + finding** when a living `require_machine` FR is GIVEUP'd by all live seats on that machine.
- **Finding after 10 minutes** when `unaccepted>0`, idle shop seats exist, and ungated `offerable=0` (fleet-wide empty offerable). State file: `{ops_home}/pin-ledger-starve.json`.

Also see `jeeves/docs/empty-offer-playbook.md` (FR #2448). Related: `jeeves/docs/monitoring.md` (idle_seats / queue_flow). Follow-ons folded here: ops playbook #2448, CAST IRON empty-offer tests #2449.
