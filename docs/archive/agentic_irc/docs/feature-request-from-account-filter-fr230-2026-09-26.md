<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-from-account-filter-fr230-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #230: sender account verification + irc_listen --from-account

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/230

## Behaviour
- `irc_agent` CAP REQ includes `account-notify`, `extended-join`, `account-tag` with `sasl` (server ACKs what it supports).
- Nick→account map in `$home/accounts.json` from ACCOUNT / extended-join / account-tag / NICK / QUIT.
- Raw tagged lines still go to `irc.log` when `AGENTIC_IRC_DEBUG=1`.
- `irc_listen --from-account <acct>` (repeatable) drops lines without that logged-in account.
- Default fleet listen behaviour unchanged (no filter unless flag set).
- Opt-in `--include-account` adds `account=` to FROM lines.

## Tests
`tests/test_account_map_fr230.py`
