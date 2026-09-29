# Functional spec: bobiverse

Pulled from LOCKED vision + session plan (2026-09-29).

## Products

1. **jeeves** MSI — Ergo (`BobIrcd`) + chair (`ircJeeves`, nick `Jeeves`).
2. **bob** MSI — ear (`ircBob`, nick `Bob-{machinename}`) + systray + Watch-AgentHealth + icons.
3. **airc** MSI — console (`Airc`, nick `{machinename}_console`).

## Behaviour summary

- Jeeves: `!register <machine>` (Simon/operators); +o all registered channels; `!recycle jeeves` restarts+updates chair.
- Bob: JOIN `#bobiverse` + `#{machine}`; on JOIN if registered get +o shop / +h bobiverse from Jeeves; listen `!recycle` / `!recycle {mid}`; systray Restart restarts `ircBob` after departure announce.
- airc: JOIN `#{mid}` if registered else `#{domain|workgroup}`.
- Agents: `{machine}-{pid}`, shop only.
- Self-update: GitHub Release MSI on service start.
- Skills installed with each MSI for agent maintain/use.
