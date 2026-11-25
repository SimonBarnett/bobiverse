# Empty offer / require_machine pin starvation (FR #2446)

Seats may hear `nothing queued` on the shop while `queue.json` still has **unaccepted** rows. The IRC line stays short on purpose (CAST IRON). The **chair log** carries the breakdown:

```text
{nick}: 0 offerable for you under focus ({U} unaccepted, {F} out-of-focus, {R} require_machine, ledger={L}, ...)
```

Built by `gitclaim.summarize_empty_offer` / `format_empty_offer_detail` (shop reply stays `format_nothing_queued` → `{nick}: nothing queued`).

**FR #7182:** idle `worker_list` seats (ready / idle on the digest) are offered within one `offer_to_idle_seats` tick even if Jeeves never said `nothing queued`. Empty-offer logs include per-job `skips=FR owner/repo#N:focus|ledger|pin|...` so "0 offerable" is explainable.

**FR #9460 (N = 30s):** when the digest shows idle/ready shop nicks and the queue still has ungated offerable rows, the chair pushes `offer_to_idle` / `push_idle_offers_via_chair_outbox` within **30 seconds** (`chair_health.IDLE_OFFER_PUSH_S`). That path does **not** wait for `!bored` and does **not** require BobAutoFeed / auto-feed config. After DONE/NACK/GIVEUP, `offer_after_done` still feeds that seat in the same tick, then a fleet idle push covers other idle seats. Ordinary idle+offerable starve must not stamp `needs_human` (ops relay `!assign` remains a backup; sibling FR covers monitor intervene).

**FR #9882 CAST IRON (primary feed path):** Jeeves offers on shop **`worker ready`** and on **`DONE`** in the same tick (`offer_focus_top` / `offer_after_done`). `!bored` is a **fallback only** when those signals were missed — not the primary way seats get work.

## When only require_machine pins remain

Typical pattern (incident 2026-10-05):

1. Focused repos have few open FRs; resync leaves only **machine-pinned** rows (`require_machine=ionos`, `redqueen`, … (CE-PRIORITY-DEV1 retired FR #6407; use `!unpin` / `!pin`)).
2. Pin machine seats **GIVEUP** the living FR → durable **seat-ledger** `giveup` blocks those nicks forever.
3. Other fleet machines cannot take the pin; pin machine has no willing seat → every `!bored` looks empty.

## Operator path (heal)

1. Read chair log empty-offer lines: confirm `require_machine` and `ledger` counts (not a blank unexplained empty).
2. Inspect seat-ledger giveup for the pin key (`owner/repo#N`) under the chair home (`.bobiverse` backup if you snapshot first).
3. Confirm digest `/report`: pin machine has **shop workers** (`worker_list`), not only `running=1` ghosts.
4. Heal options:
   - Prefer monitor auto-heal: `queue_flow` clears ledger giveup when **every live seat on the pin machine** has GIVEUP'd that pin FR (`heal_require_machine_all_gave_up`).
   - **Preferred (FR #5135):** ops PM `!cleargiveup owner/repo#N [seat]` clears queue giveup stamps + seat-ledger under the queue lock (see `jeeves-commands.md`). Prefer this over hand-editing `queue.json` / `seat-ledger.json`. **FR #9634:** `!assign <nick> …` clears that nick's give-up on the row automatically (queue + ledger) so a second `!cleargiveup` is not required before assign.
   - **Exception (FR #2486):** Living FR / Refs-only tracking umbrellas (body cue `Living FR` / `Refs-only` / `keep appending`, or labels `living` / `refs-only` / `tracking-umbrella`) are **excluded** from auto-heal so operator GIVEUPs stick (e.g. bobiverse#1993). Clear those giveups with `!cleargiveup` or an explicit manual `ledger_clear_giveup` when you intend to re-offer.
   - Manual fallback: `gitclaim.ledger_clear_giveup(home, repo, ident, nick=None, task="FR")` (omit nick to clear all), or edit ledger carefully.
5. File **unpinned** follow-up FRs so marchhare/flamingo stay fed while pins wait for the right box.
6. If pin machine has **zero** shop seats, start workers there (or clear/adjust the pin) — see monitor note `require_machine pins only; no seats on …`.

## Depends-on held vs starved (FR #9374)

Offer already skips FRs whose `Depends-on:` targets are still OPEN (or digest-gated). The stall / stuck sweep must match that gate:

- Digest `stuck` lists them as **held** with rule `depends_on_open` (or `depends_held` / `depends_unresolved`).
- They must **not** get `unaccepted_starved` or fire `stall:idle-with-work:queue`.
- When every Depends-on target closes, normal starve / idle-with-work detection resumes.

## Undispatched lookalikes (FR #9347)

Open MERGEABLE tips can look "never dispatched" for three distinct reasons:

1. **Ghost seat NAMES refuse** — digest `worker_list` still lists a departed nick; `!assign` hits NAMES timeout / not-in-shop. Chair drops that nick from the roster (`gitclaim.drop_ghost_seat_after_names_miss`) so the next offer prefers a live shop member.
2. **needs_human walls** — `giveup_count>=2` stamps `needs_human`; `!bored` will not take them. Digest `needs_human_hint` and queue_flow notes name `!cleargiveup owner/repo#N [seat]` or `!recycle`.
3. **held-pass** — MRB PASS already done; merge-on-green `skip_hold` (phase-gated). Digest/report `held_pass_count` and queue_flow `held-pass=N` — do not re-chase as MRB.

## Interim MRB author_seat heal (FR #9489)

Self-MRB / machine-id blocks can leave every idle seat refused for a tip the
fleet still needs reviewed. Queue heal options:

- Stamp `author_seat` + `implementer_seat` to a **roster** dead seat such as
  `marchhare-99999` (never invent `ghost-1` on older chairs --- enrich drops
  non-parseable nicks and recovers the real implementer).
- On tip Jeeves with FR #9489, reserved `ghost-1` (positive pid) also sticks.
- Durable: install soft machine-free MRB from FR #9478 / #9480 (PR #9482).

## Monitor (FR #2446)

`jeeves/tools/monitor/queue_flow.py`:

- **Heal + finding** when a living `require_machine` FR is GIVEUP'd by all live seats on that machine.
- **Finding after 10 minutes** when `unaccepted>0`, idle shop seats exist, and ungated `offerable=0` (fleet-wide empty offerable). State file: `{ops_home}/pin-ledger-starve.json`.
- **FR #9347 notes:** `needs_human=…` recycle hint; `held-pass=…` for phase-gated MRB PASS.

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
`copilot-mrb-backoff.json` (`mrb_fast_giveups`, epoch `mrb_backoff_until`),
written under the queue lock with atomic replacement, separate from quota.
A completed MRB PASS/FAIL verdict resets the breaker; cooldown expiry allows
new reviews but never retries rows Copilot already gave up. Set top-level
`"mrb": false` in `copilot-allowance.json` to disable cloud reviews without disabling FR/FIX
dispatch. Quota refresh does not clear this independent MRB pause.

An unaccepted, otherwise offerable MRB with no eligible live reviewer is
reported on the next stuck sweep with `rule=no_eligible_reviewer` in the
digest `stuck` list and `!stuck`; it does not wait for the generic 30-minute
starvation threshold. A busy non-author reviewer still counts as eligible.
Existing human/machine/PR holds and the no-seats/no-fuel pause remain protected.
**FR #8429 / MRB #8445:** an online digest machine with zero workers while
ungated unaccepted work is greater than 0 is reported as
`rule=online_zero_workers` (machine identity in `machine` / `holder`). That
machine finding stays visible during the no-seats pause; ordinary job-starvation
rows stay suppressed while paused.
**FR #9462:** TipForm paints a durable `online_zero_workers` alert when this
machine or a fleet peer on the digest is online with `workers=[]` and
`offerable_count > 0`. Monitor check `online_zero_workers` EXIT 1 with
fingerprint `stall:online-zero-workers:<machine>` (rate-capped). Operator
starts seats via **TipForm → Agents** — never silent auto-start (FR #3180).
The FR #5163 author-only recycle and stall scan also consult cloud eligibility.
An active tracked cloud review stays accepted: the PR being reviewed is its
input, not evidence of completed work.

After deployment, check one sweep with a sole live author seat: its abandoned
MRBs should show `no_eligible_reviewer`, and the fleet log should show one
Copilot MRB pause rather than repeated fast-GIVEUP hand-offs during cooldown.
