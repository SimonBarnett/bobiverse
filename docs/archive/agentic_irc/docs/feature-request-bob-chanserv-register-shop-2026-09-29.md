<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bob-chanserv-register-shop-2026-09-29.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #313 — bob REGISTER #{machinename} with ChanServ

## Goal

`bob-{machine}` must **REGISTER** its shop channel `#{machine}` with **ChanServ** after JOIN so founder/op survives an empty channel (Ergo otherwise only ops the creator of an ephemeral empty room).

## Acceptance

- After successful JOIN, `bob-ionos` (etc.) sends `PRIVMSG ChanServ :REGISTER #ionos` (own shop only).
- Best-effort NickServ IDENTIFY/REGISTER using `<home>/nickserv.password` (or `AGENTIC_IRC_NICKSERV_PASSWORD`) so channel registration can succeed.
- Talk seats / `w-*` / humans do **not** ChanServ-register.
- Unit tests cover line shape, bob-only gate, and password mint.
- Ergo on ionos: `channels.registration.enabled: true` and `accounts.registration.enabled: true` (PASS-gated private network).

## Out of scope

- Transferring existing channels; oper-only SAREGISTER of every historical nick.
- Changing worker JOIN rules or shop KICK policy beyond documenting ChanServ founder.

## Ionos operator action

Code is on `main`. Ergo still needs the registration knobs turned on.

**Do this on ionos:** `docs/ergo-chanserv-enable-bob-shops.md`
