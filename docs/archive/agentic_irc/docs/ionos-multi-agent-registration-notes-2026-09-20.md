<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/ionos-multi-agent-registration-notes-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Manual notes: IONOS dual Libera registration (cm-slab / cm-tweet)

**Date:** 2026-09-20  
**Host:** IONOS `WIN-MPRE8VI4U6U`  
**Channel:** `#cm-bob-oscar` (Libera)

## Observed

- `cm-slab`: `INFO joined` OK.
- `cm-tweet`: separate home `C:\Users\Administrator\.agentic-irc-tweet`, same repo `C:\Users\Administrator\agentic_irc`, no SASL env on either client.
- Tweet session: CAP LS, ident/hostname notices, `INFO no-sasl`, then timeout/reconnect loop; `irc.log` (with debug) showed no `001`.

## Expected after issue #3 build

Stdout should show explicit gates, e.g. `INFO NO 001` (not a generic `TimeoutError` only), optional `INFO reg …` lines from the server, and `INFO reconnect attempt=…` with backoff.

## Re-test checklist (Tweet / operator)

1. Confirm `--home` differs per nick (`\.agentic-irc-slab` vs `\.agentic-irc-tweet`).
2. Run second agent with `AGENTIC_IRC_DEBUG=1`; inspect `$home\irc.log` for `001` vs `ERROR`/`4xx`.
3. If still `NO 001` on Libera, configure NickServ SASL env for `cm-tweet` **or** use Ergo for dual online agents (see `docs/multi-agent-one-host.md`).
4. Offline SEAL handoff remains valid regardless of join status.

## pytest

Offline tests in `tests/test_agent.py` cover gate logging and reconnect cap parsing; no live IRC in CI.
