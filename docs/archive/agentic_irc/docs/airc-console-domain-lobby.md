<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/airc-console-domain-lobby.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR - airc console ChanServ shop vs domain lobby

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/314

## Goal

On connect, choose nick and channel from whether `#{machinename}` is
**ChanServ-registered** on Ergo:

| Shop `#{machinename}` | Channel | Nick | NickServ |
|----------------------|---------|------|----------|
| **Registered** | `#{machinename}` | `{machinename}_console` | IDENTIFY/REGISTER with existing `console.password` GUID |
| **Not registered** / probe timeout | `#{domain_or_workgroup}` for that session only | `{machinename}`, then `{machinename}_1`, `_2`, ... on 433 | Same GUID after nick settles |

## Behaviour

1. Resolve fleet `machinename` (`AIRC_CONSOLE_MACHINE` / `BOB_MACHINE_ID` / ...).
2. Resolve domain/workgroup (`--domain` / `AIRC_CONSOLE_DOMAIN` / Windows join;
   never block unbounded on WMI).
3. Connect provisionally as `{machinename}_console`.
4. After `001`, `PRIVMSG ChanServ :INFO #{machinename}` (timeout 8s -> lobby).
5. Registered -> JOIN shop as `{machinename}_console`.
6. Missing -> `NICK` to `{machinename}` (433 -> `_1`, `_2`, ...), REGISTER/IDENTIFY,
   JOIN `#{domain_or_workgroup}` only (do not also create `#{machinename}`).
7. Stay silent on the chosen channel; Query shell unchanged.

Forced modes: `--shop-mode registered|domain-lobby|auto` (env
`AIRC_CONSOLE_SHOP_MODE`).

## Acceptance

| Gate | Proof |
|------|-------|
| ChanServ registered fixture | nick `{machine}_console`, channel `#{machine}` |
| ChanServ missing / timeout | channel `#{domain}`, nick `{machine}` then `_1` on 433 |
| NickServ GUID | reuse `~\.airc-console\console.password` |
| Offline | `pytest tests/test_airc_console_fr253.py` + `--selftest` |
| Live smoke | service log shows `shop-mode=` + JOIN; operator Query still pipes |

## Non-goals

- ChanServ REGISTER of `#{machinename}` by the console
- Mode 3 / DUMB / `#bobiverse`
- Human UAT stamp from CI alone

## Layout

- `scripts/airc_console.py` - helpers + `parse_chanserv_info`
- `scripts/airc_console_service.py` - probe / JOIN state machine
- `.grok/skills/airc-console/SKILL.md`

## Issue #321

Do not block JOIN on a NICK echo after switching to the lobby nick. Ergo may
omit the confirmation; optimistic NICK then JOIN, re-JOIN on 433.

## Product call - `#workgroup` shared lobby (FR #322)

**Decision: `#workgroup` is an acceptable intentional shared lobby.** No code change.

### Why

Many Windows boxes report join type workgroup with the literal name `WORKGROUP`.
FR #314 maps that to IRC `#workgroup`. On shared Ergo (`irc.ntsa.uk`) every such
box therefore lands in the **same** lobby channel when its shop
`#{machinename}` is **not** ChanServ-registered.

That is **correct**:

| Concern | Mitigation |
|---------|------------|
| Shared channel | Machine nicks (`{machine}`, `{machine}_1`, ...) disambiguate who is who |
| Silence CAST IRON | Consoles do not PRIVMSG the lobby; Query/NOTICE shell only |
| Unwanted company | Register the shop with ChanServ (`bob-*` FR #313 / oper) so the console JOINs `#{machine}` as `{machine}_console` instead |
| Private lobby override | Set `AIRC_CONSOLE_DOMAIN` / `--domain` to a distinct id (e.g. `ce-priority-lab`) |

### Not doing (rejected for now)

- Auto-prefixing `#wg-{machine}` (defeats a shared lobby)
- Renaming default `WORKGROUP` -> `#fleet-workgroup` (same sharing, more magic)
- Code that special-cases the string `WORKGROUP` until a later product call reverses this

### Observed

CE-PRIORITY-DEV1: NetGetJoin workgroup `WORKGROUP` -> `#workgroup` while
`#ce-priority-dev1` was unregistered. Fix path for a dedicated shop: ChanServ
REGISTER `#ce-priority-dev1` (bob ear / oper), then recycle airc-console.
