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
   - **Preferred (FR #5135):** ops PM `!cleargiveup owner/repo#N [seat]` clears queue giveup stamps + seat-ledger under the queue lock (see `jeeves-commands.md`). Prefer this over hand-editing `queue.json` / `seat-ledger.json`.
   - **Exception (FR #2486):** Living FR / Refs-only tracking umbrellas (body cue `Living FR` / `Refs-only` / `keep appending`, or labels `living` / `refs-only` / `tracking-umbrella`) are **excluded** from auto-heal so operator GIVEUPs stick (e.g. bobiverse#1993). Clear those giveups with `!cleargiveup` or an explicit manual `ledger_clear_giveup` when you intend to re-offer.
   - Manual fallback: `gitclaim.ledger_clear_giveup(home, repo, ident, nick=None, task="FR")` (omit nick to clear all), or edit ledger carefully.
5. File **unpinned** follow-up FRs so marchhare/flamingo stay fed while pins wait for the right box.
6. If pin machine has **zero** shop seats, start workers there (or clear/adjust the pin) — see monitor note `require_machine pins only; no seats on …`.

## Monitor (FR #2446)

`jeeves/tools/monitor/queue_flow.py`:

- **Heal + finding** when a living `require_machine` FR is GIVEUP'd by all live seats on that machine.
- **Finding after 10 minutes** when `unaccepted>0`, idle shop seats exist, and ungated `offerable=0` (fleet-wide empty offerable). State file: `{ops_home}/pin-ledger-starve.json`.

Also see `jeeves/docs/empty-offer-playbook.md` (FR #2448). Related: `jeeves/docs/monitoring.md` (idle_seats / queue_flow). Follow-ons folded here: ops playbook #2448, CAST IRON empty-offer tests #2449.

## FR #5163 — MRB reviewer deadlock (idle seats)

When every idle seat is ineligible for every waiting MRB (exact author self-MRB
or give-up), Jeeves heals deterministically:

1. **Cross give-up** (FR #5268: two or more idle seats) — clear give-ups for
   idle *non-author* seats so an offer can proceed (no manual `!cleargiveup`).
   A sole idle seat whose give-up/cooldown is the only block is not cleared.
2. **Author-only** — only when every idle block reason is `author`: queue one
   tray `recycleseat` request (`run/recycleseat/req-*.json`, kind
   `mrb-reviewer-deadlock`), deduped and rate-limited (~180s per deadlock
   signature).

Hooked from `offer_focus_top` (same `!bored` can then stamp an offer) and
`queue_flow` monitor.

### FR #5848 — Copilot MRB backoff and no eligible reviewer

Copilot is a virtual reviewer only when its actual dispatch gates pass
(enabled, fuel available, high-priority focus, no author/GIVEUP/ledger block,
and no MRB backoff). Unlimited fuel alone does not make it eligible.
Its GIVEUP exclusions are never cleared by the cross-give-up heal, and the
virtual seat is never selected for `recycleseat`.

Three consecutive Copilot MRB GIVEUPs within 120 seconds of each task's start
pause **MRB dispatch only** for 30 minutes. State survives chair restarts in
`copilot-allowance.json` (`mrb_fast_giveups`, epoch `mrb_backoff_until`).
A completed MRB PASS/FAIL verdict resets the breaker; cooldown expiry allows
new reviews but never retries rows Copilot already gave up. Set top-level
`"mrb": false` in that file to disable cloud reviews without disabling FR/FIX
dispatch. Quota refresh does not clear this independent MRB pause.

An unaccepted, otherwise offerable MRB with no eligible live reviewer is
reported on the next stuck sweep with `rule=no_eligible_reviewer` in the
digest `stuck` list and `!stuck`; it does not wait for the generic 30-minute
starvation threshold. A busy non-author reviewer still counts as eligible.
Existing human/machine/PR holds and the no-seats/no-fuel pause remain protected.
The FR #5163 author-only recycle and stall scan also consult cloud eligibility.
An active tracked cloud review stays accepted: the PR being reviewed is its
input, not evidence of completed work.

After deployment, check one sweep with a sole live author seat: its abandoned
MRBs should show `no_eligible_reviewer`, and the fleet log should show one
Copilot MRB pause rather than repeated fast-GIVEUP hand-offs during cooldown.
