# Empty-offer starvation incident — 2026-10-05 (FR #2453)

Dated operator note for the morning **pins-only / nothing-queued** event. Playbook: [`empty-offer-playbook.md`](empty-offer-playbook.md) (FR #2448). Product heal: [#2446](https://github.com/SimonBarnett/bobiverse/issues/2446) / [PR #2450](https://github.com/SimonBarnett/bobiverse/pull/2450).

## Timeline (BST)

| When | What |
|------|------|
| ~10:31–10:40 | Shop seats (`marchhare` / `flamingo` / `ionos`) hear short `nothing queued` under focus. |
| Same window | Chair log: `0 offerable for you under focus (3 unaccepted, 0 out-of-focus, 3 require_machine)`; ionos also `ledger=1`. |
| Queue shape | Unaccepted was **pins only**: `agentic_fomprep#56` + `bobiverse#1102` (`require_machine=ce-priority-dev1`); `bobiverse#1993` (`require_machine=ionos`). |
| Ionos dual-GIVEUP | Both ionos seats were in `seat-ledger.giveup` for FR #1993 → the only ionos-eligible living FR was ledger-suppressed. |
| ce-priority workers=0 | Digest `/report` showed ce-priority-dev1 `running=1` but **0 shop workers**, so DEV1 pins could not leave via shop. |
| Focused open set | Open bobiverse issues at starvation: **2** (#1993, #1102). No open PRs. Resync did not refill offerable unpinned FRs. |

## Root cause (one line)

Offer filter was **correct**. Work **starved under focus**: backlog reduced to `require_machine` pins; ionos dual-GIVEUP blocked #1993; DEV1 pins had no shop seats.

## Mitigation that day

1. Cleared `giveup` for `simonbarnett/bobiverse#1993` (ledger backup under `.bobiverse`).
2. Direct-assigned + ACK'd #1993 → `win-mpre8vi4u6u-14452`.
3. Filed unpinned follow-up FRs so other idle machines got offerable work.
4. Product/heal path tracked as **#2446**; implementation **PR #2450** (`ledger_clear_giveup` / `heal_require_machine_all_gave_up` + `queue_flow` monitor).
5. Operator playbook landed as **FR #2448** → `empty-offer-playbook.md` (merge #2455).

## Not this note

- #2446 — product root-cause / heal acceptance.
- #2448 — standing operator playbook (not a dated incident).
- PR #2450 — code + tests for heal/monitor.

## Links

- Issue #2446: https://github.com/SimonBarnett/bobiverse/issues/2446
- PR #2450: https://github.com/SimonBarnett/bobiverse/pull/2450
- Playbook FR #2448 / doc: `jeeves/docs/empty-offer-playbook.md`
