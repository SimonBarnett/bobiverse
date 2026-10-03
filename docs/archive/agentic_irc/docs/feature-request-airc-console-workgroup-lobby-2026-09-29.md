<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-airc-console-workgroup-lobby-2026-09-29.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #322 - airc-console `#workgroup` shared lobby

## Ask

Confirm whether `#workgroup` is acceptable when Windows join is the literal
workgroup `WORKGROUP`, or whether lobby should be more specific. **No code
change until product call.**

## Product call (closed)

**Accept `#workgroup` as a shared lobby.** Documented in
`docs/airc-console-domain-lobby.md` (FR #322 section). Escape hatches:
ChanServ-register the shop, or `AIRC_CONSOLE_DOMAIN` / `--domain`.

## Non-goals

- Code special-casing the string `WORKGROUP`
- Auto `#wg-{machine}` lobbies
